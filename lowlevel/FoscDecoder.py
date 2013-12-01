#!/usr/bin/env python
# -*- coding: utf-8 -*-

import struct

def printhex(data, info="", highlight=[]):
    """ output string as hex and ASCII dump
    :param data: binary data
    :param info: info string to print in header
    :param highlight: if position (starting with 0) is in this array, print highlight
    """
    HL_ON = '\033[43m'
    HL_OFF = '\033[0m'

    if type(highlight) != list:
        highlight = []

    start = 0
    dlen = len(data)
    if info!="": info += " - "
    print "%slength: %s" % (info, dlen)
    while start < dlen:
        sub = data[start:start+16]
        slen = len(sub)

        if highlight == []:
            xc = " ".join( [c.encode("hex") for c in sub])
        else:
            pos = 0
            w = []
            ison = False
            for c in sub:
                st = ""
                hx = c.encode("hex")
                if (start+pos) in highlight:
                    if not ison:
                        st += HL_ON
                        ison = True
                    st += hx
                    if (pos==15) or not (start+1+pos) in highlight:
                        st += HL_OFF
                        ison = False
                    w.append( st )
                else:
                    w.append( hx )
                pos += 1
            xc = " ".join(w)

        padding = ((16-slen)*3)*" "
        cs = "".join( c if (ord(c) >= 32) and (ord(c) < 128) else '.' for c in sub)
        print "%04x: %s%s  %s" % (start, xc, padding, cs)

        start += 16

class datacompare(object):
    """ class to compare data blocks

    dc = datacompare()
    dc.put( datablock1 )
    dc.put( datablock2 )
    dc.put( datablock3 )
    dc.stats()
    """
    def __init__(self):
        self.basedata = None
        self.allequal = True
        self.count = 0

    def put(self,data):
        self.count += 1
        if self.basedata is None:
            self.basedata = data
            return []
        if len(self.basedata) != len(data):
            self.allequal = False
            return -1
        if self.basedata == data:
            return []
        self.allequal = False
        diff = []
        for x in range(len(data)):
            if data[x] != self.basedata[x]:
                diff.append(x)
        return diff

    def stats(self):
        if self.count > 0:
            print "Number of data blocks:", self.count
            if not self.basedata is None:
                if self.allequal:
                    print "*** All data blocks were identical"

def unpack(fmt,data):
    """ convenience unpack method
    :param fmt: struct format string
    :param data: "binary" data
    :returns: tuple with converted content
    .. note:: this functions cuts the data string according to the length required by the format string
    """
    clen = struct.calcsize(fmt)
    return struct.unpack(fmt,data[:clen])

def toBool(s):
    """ convenience function to convert byte to Boolean
    :param s: input byte
    :returns: tuple (boolean, error)
    ..note:: throws ValueError in byte is not 0 or 1
    """
    if s == 0: return False
    if s == 1: return True
    raise ValueError,"invalid value for boolean: %s" % s

def toString(s):
    """ function to extract a string from a buffer padded with zeroes
    :param s: input bytes
    :returns: cleaned string
    .. note:: throws ValueError, if padding is not zero
    """
    res = ""

    mode = 0
    for c in s:
        if mode == 0:
            if ord(c) == 0:
                mode == 1
            else:
                res += c
        elif mode == 1:
            if ord(c) != 0:
                raise ValueError,"string padding not zero"
    return res


class foss_cmd_decode(object):
    """ base decoder object

    The purpose of these objects is to
    - decode the obvious content
    - make sure that the rest remains at the value we sees so far, or raise an error if something has changed
    """
    def __init__(self, cmdno, description):
        self.cmdno = cmdno
        self.descr = description

    def cmd_no(self):
        return self.cmdno
    def description(self):
        return self.descr
    def decode(self, data):
        """ decode data
        :returns: None, if decode was successful; errormsg: if there were problems
        """
        # nothing yet, override me
        printhex(data)
        return None

class foss_cmd_0(foss_cmd_decode):
    """
    int32  command
    char4  FOSC
    int32  size
    byte   unknown1 (zero), perhaps # videostream?
    char64 username
    char64 password
    int32  uid
    char28 unknown (zeros)
    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 0, "U+P+ID 0")
    def decode(self, data):
        cmd, magic, size, un1, username, password, uid, padding  = struct.unpack("<I4sIB64s64sI28s", data)

        if un1 != 0: return "unknown1 != 0"

        username, error = unpad(username)
        if not error is None: return error

        password, error = unpad(password)
        if not error is None: return error

        padding, error = unpad(padding)
        if not error is None: return error
        if padding != "": return "Padding not empty"

        print "User/Pass/uid: %s %s %08x" % (username, password, uid)
        return None

def unpad(s):
    """ unpad a string from trailing 0x00
        make sure that all trailing zeros are actually zeros
    :param s: source string
    :returns: unpadded string, error message (or None, if ok)

    """
    res = ""
    error = None
    start = True
    for c in s:
        if start:
            if ord(c) == 0:
                start = False
            else:
                res += c
        else:
            if ord(c) != 0:
                error = "padding chars not zero %2x" % ord(c)
    return res, error


class foss_cmd_2(foss_cmd_decode):
    """
    int32  command
    char4  FOSC
    int32  size
    byte   unknown (zero)
    char64 username
    char64 password
    char32 padding (zeros)
    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 5, "U+P 2")
    def decode(self, data):
        cmd, magic, size, unknown, username, password, padding  = struct.unpack("<I4sIB64s64s32s", data)

        if unknown != 0: return "unknown != 0"

        username, error = unpad(username)
        if not error is None: return error

        password, error = unpad(password)
        if not error is None: return error

        padding, error = unpad(padding)
        if not error is None: return error
        if padding != "": return "Padding not empty"

        print "User/Pass: %s %s" % (username, password)
        return None

class foss_cmd_3(foss_cmd_decode):
    """
    int32  command
    char4  FOSC
    int32  size
    byte   unknown (zero)
    char64 username
    char64 password
    char32 padding (zeros)
    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 3, "U+P 3")
    def decode(self, data):
        cmd, magic, size, unknown, username, password, padding  = struct.unpack("<I4sIB64s64s32s", data)

        if unknown != 0: return "unknown != 0"

        username, error = unpad(username)
        if not error is None: return error

        password, error = unpad(password)
        if not error is None: return error

        padding, error = unpad(padding)
        if not error is None: return error
        if padding != "": return "Padding not empty"

        print "User/Pass: %s %s" % (username, password)
        return None

class foss_cmd_5(foss_cmd_decode):
    """
    int32  command
    char4  FOSC
    int32  size
    char64 username
    char64 password
    char32 padding (zeros)

    see also cmd 12
    note: no groupid here
    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 5, "U+P 5")
    def decode(self, data):
        cmd, magic, size, username, password, padding  = struct.unpack("<I4sI64s64s32s", data)
        username, error = unpad(username)
        if not error is None: return error

        password, error = unpad(password)
        if not error is None: return error

        padding, error = unpad(padding)
        if not error is None: return error
        if padding != "": return "Padding not empty"

        print "User/Pass: %s %s" % (username, password)
        return None

class foss_cmd_12(foss_cmd_decode):
    """
    int32  command
    char4  FOSC
    int32  size
    char64 username
    char64 password
    int32  uid
    char32 padding (zeros)
    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 12, "U+P+ID 12")
    def decode(self, data):
        cmd, magic, size, username, password, uid, padding  = struct.unpack("<I4sI64s64sI32s", data)
        username, error = unpad(username)
        if not error is None: return error

        password, error = unpad(password)
        if not error is None: return error

        padding, error = unpad(padding)
        if not error is None: return error
        if padding != "": return "Padding not empty"

        print "User/Pass/uid: %s %s %08x" % (username, password, uid)
        return None

class foss_cmd_15(foss_cmd_decode):
    """
    int32 command
    char4 FOSC
    int32 size
    int32 uid
    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 15, "keep alive request")
    def decode(self, data):
        cmd, magic, size, uid  = struct.unpack("<I4sII", data)
        print "uid %08x" % uid
        # printhex(data)
        return None

class foss_cmd_27(foss_cmd_decode):
    """
    int32 command
    char4 FOSC
    int32 size
    char12 audiohd1
    char24 audiohd2
    char1914 audiodata

    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 27, "audio in")
    def decode(self, data):
        cmd, magic, size, hd1, hd2, audiopart  = unpack("<I4sI12s24s32s", data)
        print len(data), size
        printhex(hd1,"audio-in hd1")
        printhex(hd2,"audio-in hd2")
        asize = size-36
        print "asize",asize

        if not audiodump is None:
            audiodump.write(data[48:48+asize])
        if len(data) > 48+asize:
            print "MORE"
            printhex(data[48+asize:])
        return None

class foss_cmd_29(foss_cmd_decode):
    """
    int32 command
    char4 FOSC
    int32 size
    int32 login result, 0 = ok, 1 = error
    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 29, "keep alive answer")
    def decode(self, data):
        cmd, magic, size, login = struct.unpack("<I4sII", data)
        if login == 0:
            print "Login: ok"
        elif login == 1:
            print "login: error"
        else:
            return "Unknown login result value"
        return None

class foss_cmd_108(foss_cmd_decode):
    """
    int32 command
    char4 FOSC
    int32 size
    bool mirror
    bool flip

    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 108, "show mirror/flip")
    def decode(self, data):
        cmd, magic, size, mirror, flip = struct.unpack("<I4sIBB", data)
        print mirror, flip
        try:
            mirror_fl, error = toBool(mirror)
            if not error is None: return error
            flip_fl, error = toBool(flip)
            if not error is None: return error

            print "mirror %s, flip %s" % (mirror_fl, flip_fl)
        except ValueError, e:
            print "*** Decode error: %s" % e.message
        printhex(data)
        return None

class foss_cmd_100(foss_cmd_decode):
    """
    int32  command
    char4  FOSC
    int32  size
    char8 reserved1 (zero)
    byte   number of preset points
16* char32 name of preset (max. 16), maxlen 20.
    res32  zeroes
    byte   number of walks
8* char32 name of preset (max. 8)
    res32  zeroes
    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 100, "presets, walks and more")
    def decode(self, data):
        printhex(data)
        # incomplete decdoe
        cmd, magic, size, res1, \
        numPr, pr1, pr2, pr3, pr4, pr5, pr6, pr7, pr8, pr9, pr10, pr11, pr12, pr13, pr14, pr15, pr16, res2, \
        numW, wa1, wa2, wa3, wa4, wa5, wa6, wa7, wa8, res3, res4, cameraid = \
        unpack("<I4sI8s"+
               "B32s32s32s32s32s32s32s32s32s32s32s32s32s32s32s32s32s" +
                "B32s32s32s32s32s32s32s32s32s92s12s", data)

        try:
            presets = [pr1, pr2, pr3, pr4, pr5, pr6, pr7, pr8, pr9, pr10, pr11, pr12, pr13, pr14, pr15, pr16]
            presets = [ toString(p) for p in presets]
            walks = [wa1, wa2, wa3, wa4, wa5, wa6, wa7, wa8]
            walks = [ toString(w) for w in walks]

            printhex(res2)

            print "Number of preset points",numPr
            print "Names of presets:",presets
            print "Number of cruises:", numW
            print "Name of cruises:",walks
            print "Camera ID:",cameraid
        except ValueError,e:
            print "** Decode Error: %s" % e.message

class foss_cmd_110(foss_cmd_decode):
    """
    int32 command
    char4 FOSC
    int32 size
    byte brightness
    byte contrast
    byte hue
    byte saturation
    byte sharpness
    byte denoiseLevel (nut used, value = 50)

    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 110, "show color settings")
    def decode(self, data):
        cmd, magic, size, bright, contrast, hue, saturation, sharp, denoise  = struct.unpack("<I4sIBBBBBB", data)
        print "bright %s, contrast %s, hue %s, saturation %s, sharp %s, denoise %s" % (bright, contrast, hue, saturation, sharp, denoise)
        if denoise != 50: return "denoise changed"
        return None


class foss_cmd_111(foss_cmd_decode):
    """
    int32 command
    char4 FOSC
    int32 size
    byte brightness
    byte contrast
    byte hue
    byte saturation
    byte sharpness
    byte denoiseLevel (nut used, value = 50)

    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 111, "motion detection alert")
    def decode(self, data):
        cmd, magic, size, flags  = struct.unpack("<I4sI4s", data)
        printhex(flags, "flags")
        if flags != "\x01\0x00\0x00\0x1e": return "unexpected value"
        return None

class foss_cmd_112(foss_cmd_decode):
    """
    int32 command
    char4 FOSC
    int32 size
    int32 power freq (0: 60 Hz, 1: 50 Hz, 2: outdoor)
    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 112, "show pwr freq")
    def decode(self, data):
        cmd, magic, size, mode = struct.unpack("<I4sII", data)
        decmode = {0: "60 Hz", 1:"50 Hz", 2: "outdoor"}.get(mode)
        if decmode is None:
            return "Unknown pwr freq: %s" % mode
        print "Power freq.: %s" % decmode
        return None

class foss_cmd_113(foss_cmd_decode):
    """
    int32 command
    char4 FOSC
    int32 size
    int32 stream no
    """
    def __init__(self):
        foss_cmd_decode.__init__(self, 113, "show stream no")
    def decode(self, data):
        cmd, magic, size, stream  = struct.unpack("<I4sII", data)
        print "Stream: %s" % stream
        return None


audiodump = None

def openAudioDumpFile(fnm):
    global audiodump
    audiodump = open(fnm,"wb")

def closeAudioDumpFile():
    global audiodump
    if not audiodump is None:
        audiodump.close()
    audiodump = None

decoder_list = [
            foss_cmd_0(),
            foss_cmd_2(),
            foss_cmd_3(),
            foss_cmd_5(),
            foss_cmd_12(),
            foss_cmd_15(),
            foss_cmd_27(),
            foss_cmd_29(),
            foss_cmd_108(),
            foss_cmd_100(),
            foss_cmd_110(),
            foss_cmd_111(),
            foss_cmd_112(),
            foss_cmd_113()
        ]

decoder_descriptions = { subd.cmd_no(): subd.description() for subd in decoder_list}
decoder_call = { subd.cmd_no(): subd.decode for subd in decoder_list}

# Give the decoder some means to analyse the packets
datacomp = datacompare()

