#!/usr/bin/python
# -*- coding: utf-8 -*-

import urllib, urllib2
import urlparse
import xml.dom.minidom
import re
import ConfigParser

def encode_multipart(fields, files, boundary=None):
    """
    Encodes a file in order to send it as an answer to a form
    """
    import mimetypes
    import random
    import string

    _BOUNDARY_CHARS = string.digits + string.ascii_letters

    # see http://code.activestate.com/recipes/578668-encode-multipart-form-data-for-uploading-files-via/
    def escape_quote(s):
        return s.replace('"', '\\"')

    if boundary is None:
        boundary = ''.join(random.choice(_BOUNDARY_CHARS) for i in range(30))
    lines = []

    for name, value in fields.items():
        lines.extend((
            '--{0}'.format(boundary),
            'Content-Disposition: form-data; name="{0}"'.format(escape_quote(name)),
            '',
            str(value),
        ))

    for name, value in files.items():
        filename = value['filename']
        if 'mimetype' in value:
            mimetype = value['mimetype']
        else:
            mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        lines.extend((
            '--{0}'.format(boundary),
            'Content-Disposition: form-data; name="{0}"; filename="{1}"'.format(
                    escape_quote(name), escape_quote(filename)),
            'Content-Type: {0}'.format(mimetype),
            '',
            value['content'],
        ))

    lines.extend((
        '--{0}--'.format(boundary),
        '',
    ))
    body = '\r\n'.join(lines)

    headers = {
        'Content-Type': 'multipart/form-data; boundary={0}'.format(boundary),
        'Content-Length': str(len(body)),
    }

    return (body, headers)

class DictBits(object):
    """ Helper class for bit mappings

    >>> test = DictBits( {0:"zero", 1:"one", 2:"two", 3:"three"} )
    >>> test.toArray(5)
    ['zero', 'two']
    >>> test.toInt( ["two","three"] )
    12
    >>> test.toArray(100)
    ...
    KeyError: 5
    >>> test.toInt( ["one","abcde"] )
    ...
    ValueError: option abcde not found
    """
    def __init__(self,dict):
        """
        :param dict: dictionary {bitpos1: "label1", bitpos2: "label2", ... }
        """
        self.dict = dict
        self.values = dict.values()
        self.items = dict.items()

    def toInt(self,value):
        """ generate bitmask from labels

        :param value: array with labels to convert
        :returns: bitmask
        :throws: ValueError, if label is not in dict
        """
        res = 0
        for v in value:
            if not v in self.values: raise ValueError,"option %s not found" % v
            k = [key for key,value in self.items if value==v ][0]
            res |= (1 << k)
        return res

    def toArray(self,value):
        """ create array of labels from bitmask

        :param value: integer with bitmask
        :returns: array of labels
        :throws: KeyError, if a bit is set in value whose position is not mentioned in the dict
        """
        res = []
        pos = 0
        while value != 0:
            if value & 1:
                res.append(self.dict[pos])
            value >>= 1
            pos += 1
        return res

# same for: motion detection, IO alarm
BD_alarmAction = DictBits( {0:"ring", 1:"mail", 2:"picture", 3:"video"} )
MD_sensitivity = DictBits( {"0": "low", "1": "normal", "2": "high", "3": "lower", "4": "lowest"} )

def array2dict(source,keyprefix):
    """ convert an array to dict using keys starting with keyprefix
    .. note:: used to create param dicts for sendcommand
    """
    res = {}
    count = 0
    for s in source:
        res["%s%s" % (keyprefix, count)] = s
        count += 1
    return res

def binaryarray2int(source):
    """ helper to convert array with binary strings (e.g. schedules) to integer

    :param source: the array with binary strings to convert
    :returns array with integers
    """
    res = []
    for x in source:
        res.append(int(x,2))
    return res

class resultObj(object):
    """
    create a resultObject from the XML data returned by the camera.
    XML fields will be accessible as object attributes
    """
    def __init__(self, data):
        self.data = data

        s = {
            0: "Success",
            -1: "CGI request string format error",
            -2: "Username or password error",
            -3: "Access denied",
            -4: "CGI execute failure",
            -5: "Timeout",
            -6: "Reserve",
            -7: "Unknown error",
            -8: "Reserve",
            None: "Missing result parameter",
            }.get( self.result)
        if not s is None:
            self.set("_result",s)

    def __getattr__(self,name):
        """
        make XML fields accessible as attributes
        Special treatment for "result" field: return as integer, if possible
        """
        if name == "result":
            try:
                return int(self.data.get(name))
            except ValueError:
                pass
        return self.data.get(name)

    def __str__(self):
        w = ""
        for x in self.data.keys():
            w += "%s: %s\n" % (x, self.data[x])
        return w

    def get(self,name):
        return self.__getattr__(name)

    def set(self,name,value):
        """ create (or override) attribute name with value
        """
        self.data[name] = value

    def stringLookupSet(self,value, dict, name):
        """ lookup a string in dict and set named attribute accordingly
        :param value: value to look-up
        :param dict: dictionary to look the value up
        :param name: name of the attribute to be set, if lookup was successful
        """
        if value in dict: self.set(name,dict[value])

    def collectBinaryArray(self,getparname, setparname, length):
        """ scan resultObj for similar attributes and put them into a binaray string array

         :param getparname: parameter prefix to scan in resultObj
         :param setparname: name of the parameter the result is stored into
         :param length: length of the binary string
        """
        res = []
        cnt = 0
        while True:
            p = self.get("%s%s" % (getparname,cnt))
            if p is None: break
            cnt += 1
            si = int(p)
            # add leading zeros
            w = ("0"*length)+bin(si)[2:]
            w = w[len(w)-length:]
            res.append(w)
        if w != []:
            self.set(setparname,res)

    def DB_convert2array(self,getparam, setparam, converter):
        """ helper function: get param, convert to bit mask labels and store
        :param getparam: name of the source parameter in the resultObj
        :param setparam: name of the parameter to store the result in
        :param converter: converter object of type DictBits
        """
        try:
            val = int(self.get(getparam))
            w = converter.toArray(val)
            self.set(setparam, w)
        except (ValueError, TypeError, KeyError):
            pass

class camBase(object):
    """
    basic interface to camera

    Not much processing:
    - doBool parameters are converted to/from boolean
    - string values in the returned XML are being "url-unquoted"
    - XML returned from the camera is converted into a resultObj
    - resultObj param "result" is converted to integer, if possible
    """
    def __init__(self,prot,host,port,user,password):
        """
        :param prot: protocol used ("http" or "https")
        :param host: hostname (e.g. "www.example.com")
        :param port: port used (e.g. 88 or 443)
        :param user: username of account in camera
        :param password: passwort of account in camera
        """

        self.base = "%s://%s:%s/cgi-bin/CGIProxy.fcgi" % (prot,host,port)
        self.user = user
        self.password = password

        self.debugfile = None
        self.consoleDump = False

        # GetMJStream has is special URL
        p = {"cmd": "GetMJStream", "usr": self.user, "pwd": self.password }
        ps = urllib.urlencode(p)
        self.MJStreamURL = "%s://%s:%s/cgi-bin/CGIStream.cgi?%s" % (prot,host,port,ps)


    def openDebug(self,filename):
        """ dump communication with camera into file
        :param filename: filename to dump into
        """
        self.debugfile = open(filename,"w")

    def closeDebug(self):
        """ close debug file
        """
        if not self.debugfile is None: self.debugfile.close()
        self.debugfile = None

    def setConsoleDump(self,onOff):
        """ switch debug dump to console on/off
        :param onOff: switch
        """
        self.consoleDump = onOff

    def decodeResult(self,xmldata, doBool = None):
        """decode XML resulted by API call
        :param xmldata: the xml string
        :param doBool: list of names, if parameter exists, try to convert them to a boolean value
        :return: dictionary with tags as keys
        :raises: assertion error if not exactly one `CGI_Result` tag is found

        The result is formatted like this:
            <CGI_Result>
               <tag1>....</tag1>
               <tag2>....</tag2>
               ...
            </CGI_Result>

        .. Note:: Firmware versions before 1.11.1.18 did not escape special chars and
                  could result in malformed XML files.
                  Since then, special chars are urlencoded
        """
        res = {}

        dom = xml.dom.minidom.parseString(xmldata)
        xmldata = dom.getElementsByTagName("CGI_Result")
        assert len(xmldata) == 1,"only one CGI_Result tag allowed"
        root = xmldata[0]
        for ele in root.childNodes:
            if ele.nodeType == ele.ELEMENT_NODE:
                xmldata = ""
                for sele in ele.childNodes:
                    if sele.nodeType == sele.TEXT_NODE:
                        xmldata = xmldata + sele.nodeValue
                xmldata = urllib.unquote(xmldata)
                res[ele.nodeName] = xmldata

        if not doBool is None:
            for p in doBool:
                if p in res:
                    if res[p] == "1": res[p] = True
                    if res[p] == "0": res[p] = False

        return res

    def sendcommand(self,cmd, param = None, raw = False, doBool = None, headers = None, data = None):
        """ send command to camera and return result

        :param cmd: command without parameters
        :param param:dictionary of parameter, e.g. {key1: value1, key2: value2, ...}
                     if a value is None, it will not be encoded
        :param raw: if raw, return result as is, not decoded as :class:resultObj
        :param doBool: array of names
                       if results contains these settings, try to convert them to boolean values
                       if param contains these settings, convert bool to "1"/"0"
        :param headers: headers of the request (used in POST)
        :param data:    data used for POST
        :return: resultObj with decoded data or raw data
        """

        if param is None: param = {}

        # convert boolean to "0"/"1"
        if not doBool is None:
            for p in param:
                if p in doBool:
                    if param[p] is True: param[p] = "1"
                    if param[p] is False: param[p] = "0"


        pa = {"cmd": cmd, "usr": self.user, "pwd": self.password }

        # add params not set to None
        for p in param:
            if not param[p] is None:
                pa[p] = param[p]

        ps = urllib.urlencode(pa)

        if self.consoleDump: print("%s?%s\n\n" % (self.base,ps))
        if not self.debugfile is None: self.debugfile.write("%s?%s\n\n" % (self.base,ps))
        url = self.base + "?" + ps

        if headers is None:
            retdata = urllib.urlopen(url,data = data).read()
        else:
            request = urllib2.Request(url, data = data, headers = headers)
            retdata = urllib2.urlopen(request).read()

        if self.consoleDump: print("%s\n\n" % retdata)
        if not self.debugfile is None: self.debugfile.write("%s\n\n" % (retdata))

        if raw:
            return retdata

        res = self.decodeResult(retdata, doBool = doBool)
        reso = resultObj(res)
        return reso

    # image settings
    def getImageSetting(self):   return self.sendcommand("getImageSetting")
    def setBrightness(self, brightness):   return self.sendcommand("setBrightness", {'brightness': brightness} )
    def setContrast(self, contrast):   return self.sendcommand("setContrast", {'contrast': contrast} )
    def setHue(self, hue):   return self.sendcommand("setHue", {'hue': hue} )
    def setSaturation(self, saturation):   return self.sendcommand("setSaturation", {'saturation': saturation} )
    def setSharpness(self, sharpness):   return self.sendcommand("setSharpness", {'sharpness': sharpness} )
    def resetImageSetting(self):   return self.sendcommand("resetImageSetting")
    def getMirrorAndFlipSetting(self):   return self.sendcommand("getMirrorAndFlipSetting", doBool=['isMirror','isFlip'])
    def mirrorVideo(self, isMirror):   return self.sendcommand("mirrorVideo", {'isMirror': isMirror}, doBool=["isMirror"] )
    def flipVideo(self, isFlip):   return self.sendcommand("flipVideo", {'isFlip': isFlip}, doBool=["isFlip"] )
    def setPwrFreq(self, is50hz):
        """ set power frequency of sensor
        ;param is50hz: True: 50 Hz, False: 60 Hz
        """
        return self.sendcommand("setPwrFreq", {'freq': is50hz}, doBool=["freq"] )

    def getVideoStreamParam(self):
        """
        isVBR not yet implemented by firmware
        """
        return self.sendcommand("getVideoStreamParam", doBool=['isVBR'])
    def setVideoStreamParam(self, streamType, bitRate, frameRate, GOP, isVBR):
        """
        isVBR not yet implemented by firmware
        """
        return self.sendcommand("setVideoStreamParam", {'streamType':streamType, 'bitRate': bitRate,' frameRate': frameRate, 'GOP': GOP, 'isVBR':isVBR})
    def getMainVideoStreamType(self):   return self.sendcommand("getMainVideoStreamType")
    def getSubVideoStreamType(self):   return self.sendcommand("getSubVideoStreamType", doBool=["isVBR0","isVBR1","isVBR2","isVBR3"])
    def setMainVideoStreamType(self,streamType):   return self.sendcommand("setMainVideoStreamType", {'streamType': streamType})

    def setSubVideoStreamType(self,format):
        """ format: 0: H264, 1=MJpeg
        """
        return self.sendcommand("setSubVideoStreamType", {'format': format})

    def getMJStream(self):
        """
        :returns: URL of MJPEG-Stream
        .. note: URL will return error 500 if substream has not been switched to MJPEG
        """
        return self.MJStreamURL

    def getOsdSetting(self):
        return self.sendcommand("getOSDSetting", doBool=["isEnableTimeStamp","isEnableDevName","isEnableOSDMask"])
    def setOsdSetting(self,isEnableTimeStamp,isEnableDevName,dispPos):
        """
        .. note: The parameter isEnableOSDMask which is described in the API has no effect. See setOsdMask
        """
        return self.sendcommand("setOSDSetting",
            param={'isEnableTimeStamp':isEnableTimeStamp, 'isEnableDevName':isEnableDevName, 'dispPos':dispPos },
            doBool=["isEnableTimeStamp","isEnableDevName"])

    def setOsdMask(self, isEnableOSDMask):
        """ set/reset para,eter isEnableOSDMask
        .. note: This is an undocumented CGI command
        """
        return self.sendcommand("setOSDMask",
            param={'isEnableOSDMask':isEnableOSDMask },
            doBool=["isEnableOSDMask"])
    def getOsdMask(self):
        """
        .. note: This is an undocumented CGI command
        """
        return self.sendcommand("getOSDMask", doBool=["isEnableTimeStamp","isEnableDevName","isEnableOSDMask"])

    def getOsdMaskArea(self):
        w = self.sendcommand("getOsdMaskArea")
        cnt = 0
        areas = {}
        error = False
        while True:
            p1 = w.get("x1_%s" % cnt)
            p2 = w.get("y1_%s" % cnt)
            p3 = w.get("x2_%s" % cnt)
            p4 = w.get("y2_%s" % cnt)

            if not (p1 is None or p2 is None or p3 is None or p4 is None):
                try:
                    areas[cnt] = (int(p1), int(p2), int(p3), int(p4))
                except ValueError:
                    error = True     # something is seriously wrong (new firmware?)
            else:
                break
            cnt += 1

        if not error: w.set("decoded_areas",areas)
        return w

    def setOsdMaskArea(self, areas):
        """ set OSD areas

        convert the following structure to the cameras notation:
        - there are 4 areas available
        - each area is defined by the coordinates of the upper left und bottom right point
        - Encoded as: {0: (Xtl, Ytl, Xbr, Xby), 1: ..., 3: None)
        - None means: (0,0,0,0)
        """
        maxareas = 4

        # make sure all areas are covered
        for a in range(maxareas): # 0,1,2,3
            if not a in areas:
                areas[a] = None

        # convert None to (0,0,0,0)
        for a in areas:
            if areas[a] is None:
                areas[a] = (0,0,0,0)

        # construct parameters
        params = {}
        for a in range(maxareas): # 0..3
            params["x1_%s" % a] = areas[a][0]
            params["y1_%s" % a] = areas[a][1]
            params["x2_%s" % a] = areas[a][2]
            params["y2_%s" % a] = areas[a][3]

        return self.sendcommand("setOsdMaskArea", param = params)


    def getMotionDetectConfig(self):
        return self.sendcommand("getMotionDetectConfig", doBool=["isEnable"])

    def setMotionDetectConfig(self,isEnable, linkage, snapInterval, triggerInterval,schedules,areas):
        param = {"isEnable": isEnable,
                 "linkage": linkage,
                 "triggerInterval": triggerInterval }
        for day in range(7):
            param["schedule%s" % day] = schedules[day]
        for row in range(10):
            param["area%s" % row] = areas[row]

        return self.sendcommand("setMotionDetectConfig", param = param, doBool=["isEnable"])


    # ptz commands
    def ptzReset(self):   return self.sendcommand("ptzReset")
    def ptzMoveDown(self): return self.sendcommand("ptzMoveDown")
    def ptzMoveUp(self): return self.sendcommand("ptzMoveUp")
    def ptzMoveLeft(self): return self.sendcommand("ptzMoveLeft")
    def ptzMoveTopLeft(self): return self.sendcommand("ptzMoveTopLeft")
    def ptzMoveBottomLeft(self): return self.sendcommand("ptzMoveBottomLeft")
    def ptzMoveRight(self): return self.sendcommand("ptzMoveRight")
    def ptzMoveTopRight(self): return self.sendcommand("ptzMoveTopRight")
    def ptzMoveBottomRight(self): return self.sendcommand("ptzMoveBottomRight")
    def ptzStopRun(self): return self.sendcommand("ptzStopRun")

    def getPTZPresetPointList(self): return self.sendcommand("getPTZPresetPointList")

    def getPTZSpeed(self): return self.sendcommand("getPTZSpeed")
    def setPTZSpeed(self,speed): return self.sendcommand("setPTZSpeed", {"speed": speed} )


    def zoomIn(self):   return self.sendcommand("zoomIn")
    def zoomOut(self):  return self.sendcommand("zoomOut")
    def zoomStop(self): return self.sendcommand("zoomStop")

    def setSnapSetting(self,quality,location):
        return self.sendcommand("setSnapSetting",{"snapPicQuality": quality, "saveLocation": location})

    def getWifiConfig(self): return self.sendcommand("getWifiConfig")

    # get config (data, filename) or None on error
    def exportConfig(self):
        """ queries the camera for a blob with all settings

        :return: tuple with data and filename (provided by the camera) or None (in case of an error)
        """
        w = self.sendcommand("exportConfig")

        if w.result == 0:
            link = "/configs/export/%s" % w.fileName
            link2 = urlparse.urljoin(self.base,link)
            data = urllib.urlopen(link2).read()
            return (data, w.fileName)
        else:
            return None

    def importConfig(self,filedata,filename):
        """ send config file to camera
        :param filedata: binary content of the config file
        :param filename: filename of the config file
        .. note:: camera will reboot after successful upload and not be responsive for some time
        """
        fields = {'submit': 'import'}
        files = {'file': {'filename': filename, 'content': filedata}}
        data, headers = encode_multipart(fields, files)
        return self.sendcommand("importConfig", headers = headers, data = data)


    def snapPicture(self):
        """ queries the camera for a snapshot

        :return: html file with link to image
        """

        return self.sendcommand("snapPicture", raw = True)

    def snapPicture2(self):
        """ queries the camera for a snapshot

        :return: binary data

        The firmware function has a bug which cuts off the image after 512,000 bytes.
        """
        return self.sendcommand("snapPicture2")

    def infraLed(self,state):
        """ switches the IR-LED on or off
        .. note:: Depending on the camera configuration, this may not be possible.
        :param state: on (true) or off (false)
        :return: resultObj
        """
        if state:
            return self.sendcommand("openInfraLed")
        else:
            return self.sendcommand("closeInfraLed")

    def setInfraLedConfig(self,auto):
        if auto:
            return self.sendcommand("setInfraLedConfig",{"mode": 0})
        else:
            return self.sendcommand("setInfraLedConfig",{"mode": 1})

    def getDevInfo(self):   return self.sendcommand("getDevInfo")

    def setWifiSetting(self, enable, useWifi, ap, encr, psk, auth,
         defaultKey, key1, key2, key3, key4, key1len, key2len, key3len, key4len):
        self.sendcommand("setWifiSetting", {
             "isEnable": enable,
             "isUseWifi": useWifi,
             "ssid": ap,
             "netType": 0,
             "encryptType": encr,
             "psk": psk,
             "authMode": auth,
             "defaultKey": defaultKey,
             "key1": key1,
             "key2": key2,
             "key3": key3,
             "key4": key4,
             "key1len": key1len,
             "key2len": key2len,
             "key3len": key3len,
             "key4len": key4len
        })

    def ptzAddPresetPoint(self,name):
        return self.sendcommand("ptzAddPresetPoint", {"name": name} )

    def ptzDeletePresetPoint(self,name):
        return self.sendcommand("ptzDeletePresetPoint", {"name": name} )

    def ptzGotoPresetPoint(self,name):
        return self.sendcommand("ptzGotoPresetPoint", {"name": name} )

    def ptzGetCruiseMapList(self):
        return self.sendcommand("ptzGetCruiseMapList")

    def ptzGetCruiseMapInfo(self,name):
        return self.sendcommand("ptzGetCruiseMapInfo", {"name": name} )

    def getDevState(self):  return self.sendcommand("getDevState")
    def getSnapConfig(self):
        return self.sendcommand("getSnapConfig")
    def setSnapConfig(self,quality, location):
        return self.sendcommand("setSnapConfig", {"snapPicQuality": quality, "saveLocation": location} )

    def getRecordList(self, recordPath = None, startTime = None, endTime = None, recordType = None, startNo = None):
        param = {"recordPath": recordPath,
                 "startTime": startTime,
                 "endTime": endTime,
                 "recordType": recordType,
                 "startNo": startNo }
        return self.sendcommand("getRecordList", param=param)

    def getAlarmRecordConfig(self):
        return self.sendcommand("getAlarmRecordConfig", doBool=["isEnablePreRecord"])

    def setAlarmRecordConfig(self, isEnablePreRecord, preRecordSecs, alarmRecordSecs):
        param = {"isEnablePreRecord": isEnablePreRecord,
                 "preRecordSecs": preRecordSecs,
                 "alarmRecordSecs": alarmRecordSecs }
        return self.sendcommand("setAlarmRecordConfig", param=param, doBool=["isEnablePreRecord"])

    def getIOAlarmConfig(self):
        return self.sendcommand("getIOAlarmConfig", doBool=["isEnable"])

    def setIOAlarmConfig(self, isEnable, linkage, alarmLevel, snapInterval, triggerInterval, schedules):
        param = {"isEnable": isEnable,
                 "linkage": linkage,
                 "alarmLevel": alarmLevel,
                 "snapInterval": snapInterval,
                 "triggerInterval": triggerInterval
                 }
        param.update( array2dict(schedules,"schedule") )
        return self.sendcommand("setIOAlarmConfig", param=param, doBool=["isEnable"])

    def clearIOAlarmOutput(self):
        return self.sendcommand("clearIOAlarmOutput")

    def getMultiDevList(self):
        return self.sendcommand("getMultiDevList")

    def getMultiDevDetailInfo(self,channel):
        return self.sendcommand("getMultiDevDetailInfo", param = {"chnnl": channel})

    def addMultiDev(selfself,channel, productType, ip, port, mediaPort, userName, passWord, devName):
        return self.sendcommand("addMultiDev", param = {"chnnl": channel,
                                                        "productType": productType,
                                                        "ip": ip,
                                                        "port": port,
                                                        "mediaPort": mediaPort,
                                                        "userName": userName,
                                                        "passWord": passWord,
                                                        "devName": devName })

    def delMultiDev(self,channel):
        return self.sendcommand("delMultiDev", param = {"chnnl": channel})

    def addAccount(self, usrName, usrPwd, privilege):
        return self.sendcommand("addAccount",param = {"usrName": usrName, "usrPwd": usrPwd, "privilege": privilege})

    def delAccount(self, usrName):
        return self.sendcommand("delAccount",param = {"usrName": usrName} )

    def changePassword(self, usrName, oldPwd, newPwd):
        return self.sendcommand("changePassword",param = {"usrName": usrName, "oldPwd": oldPwd, "newPwd": newPwd} )

    def changeUserName(self, usrName, newUsrName):
        return self.sendcommand("changeUserName",param = {"usrName": usrName, "newUsrName": newUsrName } )

    def getSessionList(self):
        return self.sendcommand("getSessionList")

    def getUserList(self):
        return self.sendcommand("getUserList")

    def logIn(self,name, ip=None, groupId = None):
        param = {"usrName": name}
        if not ip is None: param["ip"]=ip
        if not groupId is None: param["groupId"] = groupId
        r = self.sendcommand("logIn", param )
        if r.result == 0:
            if not r.logInResult is None:
                r.set("result", -int(r.logInResult))
        return r

    def logOut(self,name, ip=None, groupId = None):
        param = {"usrName": name}
        if not ip is None: param["ip"]=ip
        if not groupId is None: param["groupId"] = groupId
        r = self.sendcommand("logOut", param )
        return r

class cam(camBase):
    """ extended interface

    Some more conversions:
    - Conversion are usually stored in a parameter with the same name prefixed by "_"
    - Most "extended" functions use the name of the base functions followed by "_proc"
    """
    def ptzMove(self, direction):
        """ move camera into given direction or (h)ome
        :param direction:
        :return: resultObj

        The directions are:
        .         n
        .      nw   ne
        .    w    h    e
        .      sw   se
        .         s

        """
        matrix = {'n': self.ptzMoveUp, 'ne': self.ptzMoveTopRight, 'e': self.ptzMoveRight, 'se': self.ptzMoveBottomRight,
                  's': self.ptzMoveDown, 'sw': self.ptzMoveBottomLeft, 'w': self.ptzMoveLeft, 'nw': self.ptzMoveTopLeft,
                  'h': self.ptzReset }
        fkt = matrix.get(direction.lower())
        assert not fkt is None,"Invalid ptz direction"
        return fkt()

    def snapPicture_proc(self):
        """ gets a snapshot from the camera
        :returns: (binary data, filename from html) or (None, None) on error
        .. note:: This higher function uses the :func:`snapPicture` API call, as :func:`snapPicture2` is currently
                  limited to 512,000 bytes (bug in firmware)
        """
        w = self.snapPicture()
        # <html><body><img src="../snapPic/Snap_20131027-114838.jpg"/></body></html>
        res = re.search("img src=\"(.+)\"",w)
        if res is None: return (None, None)

        link = res.group(1)
        ipath = urlparse.urlsplit(link).path
        p = ipath.rfind("/")

        if p == -1: return (None, None)
        fname = ipath[p+1:]

        link2 = urlparse.urljoin(self.base,link)

        data = urllib.urlopen(link2).read()
        return (data, fname)

    def getPTZSpeed_proc(self):
        _ptzSpeedList = {"4": 'very slow', "3": 'slow', "2": 'normal speed', "1": 'fast', "0": 'very fast'}
        res = self.sendcommand("getPTZSpeed")
        res.stringLookupSet(res.speed, _ptzSpeedList, "_speed")
        return res

    def getPTZPresetPointList_proc(self):
        """ queries the device for a list of preset points

        :return: unsorted python string list
        """
        res = []
        w = self.getPTZPresetPointList()

        try:
            poicnt = int(w.cnt)
        except ValueError:
            return []

        for x in range(poicnt):
            d = w.get("point%s" % x)
            res.append(d)
        return res

    def activateOsdMaskArea(self, areas):
        """ activates OSD mask areas
        :param areas: area definition {0: (x1,y2,x2,y2), 1: ..., 3: ...}
        """
        res = self.setOsdMask(isEnableOSDMask = True)
        if res.result == 0:
            self.setOsdMaskArea(areas)

    def deactivateOsdmask(self):
        """ deactivates the OsdMask(s)
        """
        res = self.setOsdMask(isEnableOSDMask = False)
        if res.result == 0:
            # send the command twice
            # a single call does not switch it off reliably
            self.setOsdMask(isEnableOSDMask = False)

    # this function sets WPA config only
    def setWifiSettingWPA(self, enable, useWifi, ap, encr, psk, auth):
        self.setWifiSetting(enable, useWifi, ap, encr, psk, auth,
            1, "", "", "", "", 64, 64, 64, 64)

    def getMotionDetectConfig_proc(self):
        """ get motion detection configuration with decoded information

        The following information is decoded:
        _areas: 10x10 active areas in frame -> array of 10 strings, each strings contains 10 times "1"/"0" for active/non active
        _schedules: 7 strings of 48 chars, one for each day (starting with monday)
                  each string contains "1"/"0" for each half hour of the day
        _linkage: array of alarm action
        """

        _motionDetectSensitivity = {"0": "low", "1": "normal", "2": "high", "3": "lower", "4": "lowest"}
        res = self.getMotionDetectConfig()
        res.stringLookupSet(res.sensitivty,_motionDetectSensitivity,"_sensitivity")

        res.collectBinaryArray("schedule","_schedules",48)
        res.collectBinaryArray("area","_areas",10)
        res.DB_convert2array("linkage","_linkage", BD_alarmAction)

        return res

    def setMotionDetectConfig_proc(self,isEnable, linkage, snapInterval, triggerInterval,schedules,areas):
        self.setMotionDetectConfig(
            isEnable,
            BD_alarmAction.toInt(linkage),
            snapInterval,
            triggerInterval,
            binaryarray2int(schedules),
            binaryarray2int(areas) )

    def getSnapConfig_proc(self):
        res = self.sendcommand("getSnapConfig")
        res.stringLookupSet(res.snapPicQuality,
            {"0":"low", "1": "normal", "2": "high"},
            "_snapPicQuality")
        res.stringLookupSet(res.saveLocation,
            {"0":"SD card", "1": "reserved", "2": "FTP"},
            "_saveLocation")
        return res

    def getIOAlarmConfig_proc(self):
        res = self.getIOAlarmConfig()
        res.collectBinaryArray("schedule","_schedules",48)
        res.DB_convert2array("linkage","_linkage", BD_alarmAction)
        return res

    def setIOAlarmConfig_proc(self,isEnable, linkage, alarmLevel, snapInterval, triggerInterval, schedules ):
        res = self.setIOAlarmConfig(
            isEnable,
            BD_alarmAction.toInt(linkage),
            alarmLevel,
            snapInterval,
            triggerInterval,
            binaryarray2int(schedules) )
        return res

if __name__ == "__main__":
    config = ConfigParser.ConfigParser()

    # see cam.cfg.example
    config.readfp(open('cam.cfg'))
    prot = config.get('general','protocol')
    host = config.get('general','host')
    port = config.get('general','port')
    user = config.get('general','user')
    passwd = config.get('general','password')

    # connection to the camera
    do = cam(prot,host,port,user,passwd)

    # display basic camera info
    res = do.getDevInfo()
    if res.result == 0:       # quick check
        print """product name: %s
serial number: %s
camera name: %s
firmware version: %s
hardware version: %s""" % (res.productName, res.serialNo, res.devName, res.firmwareVer, res.hardwareVer)
    else:
        print res._result
