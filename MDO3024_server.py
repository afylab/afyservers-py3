from labrad import types as T, util
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as U

from struct import unpack_from

import numpy as np
import matplotlib.pyplot as plt
import re

from scipy import signal

COUPLINGS = ['AC', 'DC']
VERT_DIVISIONS = 5.0
HORZ_DIVISIONS = 10.0
SCALES = []

"""
### BEGIN NODE INFO
[info]
name = MDO3024 Server
version = 1.0
description =
[startup]
cmdline = %PYTHON% %FILE%
timeout = 20
[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

class MDO3024Wrapper(GPIBDeviceWrapper):
    pass

class MDO3024Server(GPIBManagedServer):
    name = 'TEKTRONIX MDO3024'
    deviceName = 'TEKTRONIX MDO3024'
    deviceWrapper = MDO3024Wrapper
    
    @setting(111, returns=['s'])
    def ident(self, c):
        """Returns the oscilloscope identification code."""
        dev = self.selectedDevice(c)
        resp = yield dev.query('*IDN?')
        returnValue(resp)
    
    @setting(112, returns=[])
    def reset(self, c):
        """Resets oscilloscope settings to factory default settings."""
        dev = self.selectedDevice(c)
        yield dev.write('*RST')
        #add a wait time to allow the device to reset?
        
    @setting(113, returns=[])
    def clears(self, c):
        """Clears the event queue, standard event status register, and the status byte register."""
        dev = self.selectedDevice(c)
        yield dev.write('*CLS')    
        
    @setting(114, returns=['s'])
    def busy(self, c):
        """Returns the status of the oscilloscope. If it is currently busy returns :BUSY 1 and if it is not busy returns :BUSY 0. """
        dev = self.selectedDevice(c)
        yield dev.write('BUSY?')    
        
    @setting(115, returns=[])
    def calibrate(self, c):
        """Performs an internal self-calibration and returns the calibration status. Response :CAL 1 indicates the calibration did not complete successfully, and response :CAL 0 indicates the calibration completed successfully."""
        dev = self.selectedDevice(c)
        yield dev.write('*CAL?')
        
    @setting(116, channel = 'i', returns = 'vsvvvvvsv')
    def chsettings(self, c, channel):
        """Gets information about an oscilloscope channel (1-4). Returns an eight-tuple consisting of the following settings: (ProbeAttenuation, Termination, Verical Scale, Vertical Position, Coupling, Bandwidth Limit, Inversion, Vertical Units)"""
        dev = self.selectedDevice(c)
        resp = yield dev.query('CH%d?' %channel)
        ampsViaVoltsStat, ampsViaVoltsFactor, probe, chLabel, gain, probeUnit, vparam0, vparam1, vparam2, vparam3, bandWidth, coupling, deskew, vOffset, inversion, vPos, vScale, vUnits, termination, vparam4 = resp.split(';')
        
        
        ampsViaVoltsFactor = T.Value(float(ampsViaVoltsFactor), '')
        gain = T.Value(float(gain), '')
        bandWidth = T.Value(float(bandWidth), '')
        deskew = T.Value(float(deskew), '')
        vOffset = T.Value(float(vOffset), '')
        inversion = T.Value(float(inversion), '')
        vPos = T.Value(float(vPos), '')
        vScale = T.Value(float(vScale), '')
        termination = T.Value(float(termination), '')
        vUnits = vUnits[1:-1]
        
        returnValue((bandWidth, coupling, deskew, vOffset, inversion, vPos, vScale, vUnits, termination))
        
    @setting(117, channel = 'i', coupling = 's', returns=['s'])
    def coupling(self, c, channel, coupling = None):
        """Gets or sets the coupling of a given channel. Accepts either "AC" or "DC" as the coupling setting. When the coupling has been reset, the device responds with the coupling."""
        dev = self.selectedDevice(c)
        if coupling is None:
            resp = yield dev.query('CH%d:COUPling?' %channel)
        else:
            coupling = coupling.upper()
            if coupling not in COUPLINGS:
                raise Exception('Coupling must be either "AC" or "DC".')
            else:
                yield dev.write(('CH%d:COUPling'+' '+coupling) %channel)
                resp = yield dev.query('CH%d:COUPling?' %channel)
        returnValue(resp)

    @setting(118, channel = 'i', scale = 'v', returns=['v'])
    def vscale(self, c, channel, scale = None):
        """Gets or sets the vertical scale of a given channel. Requires a floating point scale which is read in Volts per division (eg a scale of 100E-03 sets the vertical scale to 100 mV per division). Once the scale has been reset the device returns the scale."""
        dev = self.selectedDevice(c)
        if scale is None:
            resp = yield dev.query('CH%d:SCale?' %channel)
        else:
            scale = format(scale, 'E')
            yield dev.write(('CH%d:SCale'+' '+scale) %channel)
            resp = yield dev.query('CH%d:SCale?' %channel)

        returnValue(resp)
        
    @setting(119, channel = 'i', inversion = 's', returns=['s'])
    def inversion(self, c, channel, inversion = None):
        """Gets or sets the the inversion of a given channel. Requires an inversion of either "ON" or "OFF"."""
        dev = self.selectedDevice(c)
        if inversion is None:
            resp = yield dev.query('CH%d:INVert?' %channel)
        else:
            INVERSIONS = ['ON', 'OFF']
            inversion = inversion.upper()
            if inversion not in INVERSIONS:
                raise Exception('Inversion must be either "ON" or "OFF".')
            else:
                yield dev.write(('CH%d:INVert'+' '+inversion) %channel)
                resp = yield dev.query('CH%d:INVert?' %channel)
        
        returnValue(resp)
        
    @setting(120, channel = 'i', offset = 'v', returns=['v'])
    def voffset(self, c, channel, offset = None):
        """Sets the vertical offset of a given channel. Returns the value of the offset in Volts. The vertical offset adjusts the vertical center of the acquisition window and determines what range of data (on the vertical axis) are recorded. The range of appropriate offset values depends on the vertical scale and input impedence of a channel. For guidelines on  offset ranges, consult the MDO3000 series programmer manual p.2-216"""
        dev = self.selectedDevice(c)
        if offset is None:
            resp = yield dev.query('CH%d:OFFSet?' %channel)
        else:
            offset = format(offset, 'E')
            yield dev.write(('CH%d:OFFSet'+' '+offset) %channel)
            resp = yield dev.query('CH%d:OFFSet?' %channel)

        returnValue(resp)

    @setting(121, channel = 'i', avv = 'i', returns = ['s'])
    def ampsviavolts(self, c, channel, avv = None):
        """Get the status of or enable Amps via Volts for a given channel. Input 1 to turn Amp via Volts on and 0 to turn it off"""
        dev = self.selectedDevice(c)
        if avv is None:
            resp = yield dev.query('CH%d:AMPSVIAVOLTs:ENAble?' %channel)
        else:
            yield dev.write('CH%d:AMPSVIAVOLTs:ENAble %d' %(channel , avv))
            resp = yield dev.query('CH%d:AMPSVIAVOLTs:ENAble?' %channel)
        returnValue(resp)            
                        
        
    @setting(122, channel = 'i', factor = 'v', returns = ['v'])
    def ampsviavoltsfactor(self, c, channel, factor = None):
        """Get or set the amps via volts factor for a given channel."""
        dev = self.selectedDevice(c)
        if ampsviavolts is None:
            resp = yield dev.query('CH%d:AMPSVIAVOLTS:FACtor?' %channel)
        else:
            yield dev.write('CH%d:AMPSVIAVOLTS:FACtor %r' %(channel, factor))
            resp = yield dev.query('CH%d:AMPSVIAVOLTS:FACtor?' %channel)
        returnValue(resp)
    
    @setting(123, channel = 'i', bandwidth = 's', returns = ['v'])
    def bandwidth(self, c, channel, bandwidth = None):
        """Get or set the bandwidth of a given channel."""
        dev = self.selectedDevice(c)
        if bandwidth is None:
            resp = yield dev.query('CH%d:BANdwidth?' %channel)
        else:
            band = format(bandwidth, 'E')
            yield dev.write(('CH%d:BANdwidth' + ' ' + band) %channel)
            resp = yield dev.query('CH%d:BANdwidth?' %channel)
        returnValue(resp)
        
    @setting(124, channel = 'i', deskew = 'v', returns = ['v'])
    def deskew(self, c, channel, deskew = None):
        """Get or set the deskew time of a given channel."""
        dev = self.selectedDevice(c)
        if deskew is None:
            resp = yield dev.query('CH%d:DESKew?' %channel)
        else:
            yield dev.write('CH%d:DESKew %r' %(channel , deskew))
            resp = yield dev.query('CH%d:DESKew?' %channel)
            
        resp = float(resp)    
        returnValue(resp)
        
    @setting(125, channel = 'i', vposition = 'v', returns = ['v'])
    def vposition(self, c, channel, vposition = None):
        """Get or set the vertical position of a given channel."""
        dev = self.selectedDevice(c)
        if vposition is None:
            resp = yield dev.query('CH%d:POSition?' %channel)
        else:
            vposition = format(vposition, 'E')
            yield dev.write(('CH%d:POSition' + ' ' + vposition) %channel)
            resp = yield dev.query('CH%d:POSition?' %channel)
        returnValue(resp)
        
    @setting(126, channel = 'i', termination = 's', returns = ['v'])
    def termination(self, c, channel, termination = None):
        """Get or set the termination reisitance of a given channel. The termination must be set to either 50 Ohm or 1 MOhm by giving a termination of "FIFty" or MEG" respectively."""
        dev = self.selectedDevice(c)
        TERMINATIONS = ['FIFty', 'MEG']
        if termination is None:
            resp = yield dev.query('CH%d:TERmination?' %channel)
        else:
            if termination not in TERMINATIONS:
                raise EXception('Termination must be either "FIFty" or "MEG".')
            else:
                yield dev.write(('CH%d:TERmination' + ' ' + termination) %channel)
                resp = yield dev.query('CH%d:TERmination?' %channel)
                
        returnValue(resp)

    @setting(127, channel = 'i', label = 's', returns = ['s'])
    def chlabel(self, c, channel, label = None):
        """Get or set the label of a given channel."""
        dev = self.selectedDevice(c)
        if label is None:
            resp = yield dev.query('CH%d:LABel?' %channel)
        else:
            yield dev.write('CH%d:LABel %s' %(channel , label))
            resp = yield dev.query('CH%d:LABel?' %channel)
        returnValue(resp)        
        
    @setting(128, channel = 'i', gain = 'v', returns = ['v'])
    def chgain(self, c, channel, gain = None):
        """Get or set the gain for the probe attached to a given channel."""
        dev = self.selectedDevice(c)
        if gain is None:
            resp = yield dev.query('CH%d:PRObe:GAIN?' %channel)
        else:
            yield dev.write('CH%d:GAIN %r' %(channel , gain))
            resp = yield dev.query('CH%d:GAIN?' %channel)
        returnValue(resp)        
        
    @setting(129, channel = 'i', signal = 's', returns = ['s'])
    def chsignal(self, c, channel, signal = None):
        """Get or set the signal for the probe attached to a given channel."""
        dev = self.selectedDevice(c)
        if signal is None:
            resp = yield dev.query('CH%d:PRObe:SIGnal?' %channel)
        else:
            yield dev.write('CH%d:SIGnal %s' %(channel , signal))
            resp = yield dev.query('CH%d:SIGnal?' %channel)
        returnValue(resp)            
        
    @setting(130, scale = 'v', returns= ['v'])
    def hscale(self,c,scale = None):
        """Get or set the time-base horizontal scale and returns the newly set scale in seconds/Division."""
        dev = self.selectedDevice(c)
        if scale is None:
            resp = dev.query('HORizontal:SCAle?')
        else:
            yield dev.write(('HORizontal:SCAle %r')  %scale)
            resp = yield dev.query('HORizontal:SCAle?')

        returnValue(resp)
        
    @setting(131, channel = 'i', start ='i', stop = 'i', returns = '**v[]')
    def gettrace(self, c, channel, start, stop):
        """Records a trace from the oscilloscope from a specified start point to a specified end point. Specify a channel, a start point from which the oscilloscope will begin taking data, and a stop point at which the scope will stop taking data. The number of horizontal increments on the display screen is set by the record length, so the start and stop values should be between 1 and the record length. The oscilloscope will return a list of ordered pairs with units (seconds, Volts)."""
        dev = self.selectedDevice(c)
        trace_points = stop - start + 1
        yield dev.write('DATA:SOURCE CH%d' %channel)
        yield dev.write('DATA:START %d' %start)
        yield dev.write('DATA:STOP %d' %stop)
        yield dev.write('DATa:ENCdg FAStest')

        yield dev.write('DATa:WIDth 2')
        yield dev.write('HEADer 0')
        yield dev.write('VERBose 0')
        pream = yield dev.query('WFMOUTpre?')

        voltsPerDiv, voltUnits, secPerDiv, timeUnits, xincr, xzero, ymult, yoff, yzero = parsepream(pream)

        voltdata = yield dev.query('CURVE?')

        tracedata = []
        voltdata = unpack_from('>%dh' %trace_points ,voltdata,len(voltdata)-2*trace_points)

        for i in range(0,len(voltdata)):
            tracedata.append([xincr * i ,(float(voltdata[i]) - yoff) * ymult + yzero])

        returnValue(tracedata)

    @setting(132, channel = 'i', returns = '*(v[s], v[V])')
    def chacquire(self, c, channel):
        """Records a trace from the oscilloscope for a specified channel. The oscilloscope records the trace of the specified channel acros the entrie display screen and will return a list of ordered pairs with units (seconds, Volts)."""
        dev = self.selectedDevice(c)
        recordlength = 100000
        yield dev.write('DATA:SOURCE CH%d' %channel)
        yield dev.write('DATA:START 1')
        yield dev.write('DATA:STOP 100000')
        yield dev.write('DATa:WIDth 2')
        yield dev.write('DATa:ENCdg ASCIi')
        yield dev.write('HEADer 0')
        yield dev.write('VERBose 0')
        pream = yield dev.query('WFMOUTpre?')
        voltsPerDiv, voltUnits, secPerDiv, timeUnits, xincr, xzero, ymult, yoff, yzero = parsepream(pream)
        voltdata = yield dev.query('CURVE?')
        tracedata = []
        voltdata = voltdata.split(',')
        for i in range(0,len(voltdata)):
            tracedata.append(( xincr * i * U.s, ((float(voltdata[i]) - yoff) * ymult + yzero)*U.V))
        
        #xs = [x[0] for x in tracedata]
        #ys = [x[1] for x in tracedata]
        #plt.plot(xs, ys)
        #plt.show()
        returnValue(tracedata)
        
    @setting(133,  returns= ('vsvsvvvvv'))
    def wfmpreamble(self,c):
        """Returns the waveform preable."""
        dev = self.selectedDevice(c)
        yield dev.write('HEADer 0')
        yield dev.write('VERBose 0')
        pream = yield dev.query('WFMOUTpre?')
        voltsPerDiv, voltUnits, secPerDiv, timeUnits, xincr, xzero, ymult, yoff, yzero = parsepream(pream)
        returnValue((voltsPerDiv, voltUnits, secPerDiv, timeUnits, xincr, xzero, ymult, yoff, yzero))
        
    @setting(134,  returns= ['s'])
    def waveform(self,c):
        """Returns the waveform."""
        dev = self.selectedDevice(c)
        resp = yield dev.query('WAVFrm?')
        returnValue(resp)        
        
        
    @setting(135,  returns= ['s'])
    def data(self,c):
        """Returns the waveform data settings."""
        dev = self.selectedDevice(c)
        resp = yield dev.query('DATA?')
        returnValue(resp)            
        
        
    @setting(136,  returns= '*v {volts}')
    def curve(self,c):
        """Returns the waveform data settings."""
        dev = self.selectedDevice(c)
        resp = yield dev.query('CURVE?')
        data = []
        resp = resp.split(',')
        for i in range(0,len(resp)):
            data.append(float(resp[i]))
        returnValue(data)            
        
        
    @setting(137,  width = 'i', returns= ['s'])
    def datawidth(self,c,width):
        """Returns the waveform data settings."""
        dev = self.selectedDevice(c)
        yield dev.write('DATa:WIDth %d' %width)
        resp = yield dev.query('DATA:WIDth?')
        returnValue(resp)    
    
    @setting(138, channel = 'i',maths = 's',  returns = ('sss'))
    def mathchdef(self, c, channel,  maths = None):    
        """Allows the defintion of a math channel. Input an integer to indicate the channel number and an expression of the form "(CH1 + CH2) / 2"  as the definition."""
        dev = self.selectedDevice(c)
        if maths is None:
            resp = yield dev.query('MATH:DEFINE?')
            type = yield dev.query('MATH%d:TYPE?' %channel)
            math = yield dev.query('MATH?')
        else:
            yield dev.write('MATH%d:TYPe ADVanced' %channel)
            yield dev.write('MATH:AUTOSCALE OFF')
            yield dev.write(('MATH%d:DEFINE "%s"') %(channel, maths))
            resp = yield dev.query('MATH:DEFINE?')
            type = yield dev.query('MATH%d:TYPE?' %channel)
            math = yield dev.query('MATH?')
        returnValue((resp, type, math))
        
    @setting(139, channel = 'i', start ='i', stop = 'i', returns = '*(v[s], v[V])')
    def getmathtrace(self, c, channel, start, stop):
        """Records a trace from the oscilloscope. Specify a channel, a start point from which the oscilloscope will begin taking data, and a stop point at which the scope will stop taking data. The oscilloscope will return an array of floating point numbers in ASCIi."""
        dev = self.selectedDevice(c)
        yield dev.write('SELECT:MATH 1')
        recordlength = stop - start + 1
        yield dev.write('DATA:SOURCE MATH%d' %channel)
        yield dev.write('DATA:START %d' %start)
        yield dev.write('DATA:STOP %d' %stop)
        yield dev.write('DATa:WIDth 1')
        yield dev.write('DATa:ENCdg ASCIi')
        yield dev.write('HEADer 0')
        yield dev.write('VERBose 0')
        xincr = yield dev.query('MATH:HORIZONTAL:SCALE?' )
        xincr = float(xincr)
        yscale = yield dev.query('MATH:VERTICAL:SCALE?' )
        yscale = float(yscale)
        yoff = yield dev.query('MATH:VERTICAL:POSITION?')
        yoff = float(yoff)
        voltdata = yield dev.query('CURVE?')
        tracedata = []
        voltdata = voltdata.split(',')
        for i in range(0,len(voltdata)):
            tracedata.append(( xincr * i * U.s, ((float(voltdata[i]) - yoff) * ymult + yzero)*U.V))
        
        #xs = [x[0] for x in tracedata]
        #ys = [x[1] for x in tracedata]
        #plt.plot(xs, ys)
        #plt.show()
        yield dev.write('SELECT:MATH 0')
        returnValue(tracedata)

    @setting(140, channel = 'i', status = 'i', returns = 's')
    def chonoff(self, c, channel, status = None):
        """Gets the status of a cahnnel or turns a specified channel on or off on the display. To turn a channel on input (channel #, 1) to turn a channel off input (channel #, 0)."""
        dev = self.selectedDevice(c)
        if status is None:
            resp = yield dev.query('SELECT:CH%d?' %channel)
        else:
            yield dev.write(('SELECT:CH%d %d') %(channel, status))
            resp = yield dev.query('SELECT:CH%d?' %channel)
        returnValue(resp)
        
    @setting(141, status = 'i', returns = 's')
    def mathchonoff(self, c, status = None):
        """Gets the status of the math channel or turns the math channel on or off. To turn teh math channel on input (channel #, 1) to turn the math channel off input (channel #, 0)."""
        dev = self.selectedDevice(c)
        if status is None:
            resp = yield dev.query('SELECT:MATH?')
        else:
            yield dev.write('SELECT:MATH %d' %status)
            resp = yield dev.query('SELECT:MATH?')
            
        returnValue(resp)
        
    @setting(142, returns = 'v[]')
    def recordlengthoptions(self,c):
        '''This query returns a list of supported record lengths for the analog channels.'''
        dev = self.selectedDevice(c)
        string = yield dev.query('CONFIGuration:ANALOg:RECLENS?')
        
        list = [1000,10000,100000,1000000,5000000,10000000]
        returnValue(list)
        
    @setting(143, length = 'i', returns = 'v')
    def recordlength(self,c, length = None):
        '''This sets the record length to closest supported record length to the specified length, then returns the set length'''
        dev = self.selectedDevice(c)
        
        if length is not None:
            yield dev.write(('HORizontal:RECOrdlength %d')  %length)
        resp = yield dev.query('HORizontal:RECOrdlength?')
    
        returnValue(resp)
        
    @setting(144, channel = 'i', record_length ='i', trace_length = 'v[]', FFT_points = 'i', returns = '**v[]')
    def gettraceFFT(self, c, channel, record_length, trace_length, FFT_points):
        """Records a full trace from the oscilloscope from a specified start point to a specified end point. Performs a FFT using Welch's algorithm on the data and returns the FFT in pairs of (Hz, Volts/root Hz)."""
        dev = self.selectedDevice(c)
        yield self.recordlength(c, record_length)
        yield self.hscale(c, trace_length/10)
        sampling_freq = record_length / trace_length

        data = yield self.gettrace(c, channel,1,record_length)

        
        volts = []
        for j in range(0,record_length):
            volts.append(data[j][1])
            
        freqs, FFT = signal.welch(volts,sampling_freq, nperseg = FFT_points, )

        formatted_data = []
        data_length = len(FFT)
        for j in range (0,data_length):
            formatted_data.append([freqs[j],FFT[j]])

        returnValue(formatted_data)
        
def parsepream(preamble):
    preamble = preamble.split(';')
    divinfo =  preamble[5].split(',')
    vscale = divinfo[2]
    hscale = divinfo[3]
    xincr = float(preamble[10])
    xzero = float(preamble[11])
    ymult = float(preamble[14])
    yoff = float(preamble[15])
    yzero = float(preamble[16])
    
    def parseString(string): # use 'regular expressions' to parse the string
        number = re.sub(r'.*?([\d\.]+).*', r'\1', string)
        units = re.sub(r'.*?([a-zA-z]+)/.*', r'\1', string)
        return float(number), units
        
    voltsPerDiv, voltUnits = parseString(vscale)
    secPerDiv, timeUnits = parseString(hscale)
    return(voltsPerDiv, voltUnits, secPerDiv, timeUnits, xincr, xzero, ymult, yoff, yzero)    
        
        
        
        
        
__server__ = MDO3024Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)    