# Copyright (C) 2011 Peter O'Malley/Charles Neill
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
### BEGIN NODE INFO
[info]
name = sr860
version = 2.7
description =
[startup]
cmdline = %PYTHON% %FILE%
timeout = 20
[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from math import log10
from labrad import types as T, gpib, units
from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import numpy as np

def getTC(i):
    ''' converts from the integer label used by the SR860 to a time '''
    if i < 0:
        return getTC(0)
    elif i > 21:
        return getTC(21)
    elif i % 2 == 0:
        return 10**(-6 + i//2)
    else:
        return 3*10**(-6 + i//2)

def getSensitivity(i):
    ''' converts form the integer label used by the SR860 to a sensitivity '''
    if i < 0:
        return getSensitivity(0)
    elif i > 27:
        return getSensitivity(27)
    elif i % 3 == 0:
        return 10**(-i//3)
    elif i % 3 == 1:
        return 5 * 10**(-i//3)
    else:
        return 2 * 10**(-i//3)

def getSensitivityInt(v, mode):
    ''' converty from real sensitivity to an integer value taken by the sr860'''
    if mode == 0:
        sens = int(round(3*log10(v)))+26
    else:
        sens = int(round(3*log10(v)))+2
    return sens

def getTCInt(t):
    ''' convert from real sensitivity values to an integer value taken by the sr860'''
    timeconstant = int(2+round(2*log10(t)))+10
    return timeconstant



def getSensitivityInt(v, mode):
    ''' converty from real sensitivity to an integer value taken by the sr860'''
    if mode == 0:
        sens = -int(round(3*log10(v)))
    else:
        sens = -int(round(3*log10(v*1e6)))
    return sens


class sr860Wrapper(GPIBDeviceWrapper):
    @inlineCallbacks
    def inputMode(self):
        mode = yield self.query('ISRC?')
        returnValue(int(mode))

    @inlineCallbacks
    def tbmode(self, mode = None):
        if mode is None:
            resp = yield self.query('TBMODE?')
            returnValue(int(resp))
        else:
            yield self.write('TBMODE  ' + str(mode))
            resp = yield self.query('TBMODE?')
            returnValue(int(resp))

    @inlineCallbacks
    def freqext(self):
        resp = yield  self.query('FREQEXT?')
        returnValue(float(resp))

    @inlineCallbacks
    def phase(self, ph = None):
        if ph is None:
            resp = yield self.query('PHAS?')
            returnValue(float(resp))
        else:
            yield self.write('PHAS ' + str(ph))
            resp = yield self.query('PHAS?')
            returnValue(float(resp))

    @inlineCallbacks
    def reference(self,ref = None):
        if ref is None:
            resp = yield self.query('RSRC?')
            returnValue(int(resp))
        else:
            yield self.write('RSRC ' + str(ref))
            resp = yield self.query('RSRC?')
            returnValue(int(resp))

    @inlineCallbacks
    def frequency(self, f = None):
        if f is None:
            resp = yield self.query('FREQ?')
            returnValue(float(resp))
        else:
            yield self.write('FREQ ' + str(f))
            resp = yield self.query('FREQ?')
            returnValue(float(resp))

    @inlineCallbacks
    def external_reference_slope(self,  ers = None):
        if ers is None:
            resp = yield self.query('RSLP?')
            returnValue(int(resp))
        else:
            yield self.write('RSLP ' + str(ers))
            resp = yield self.query('RSLP?')
            returnValue(resp)

    @inlineCallbacks
    def harmonic(self,  h = None):
        if h is None:
            resp = yield self.query('HARM?')
            returnValue(int(resp))
        else:
            yield self.write('HARM ' + str(h))
            resp = yield self.query('HARM?')
            returnValue(int(resp))

    @inlineCallbacks
    def gnd_mode(self,  mode = None):
        if mode is None:
            resp = yield self.query('IGND?')
            returnValue(int(resp))
        else:
            yield self.write('IGND ' + str(mode))
            resp = yield self.query('IGND?')
            returnValue(int(resp))

    @inlineCallbacks
    def curr_gain(self,  gain = None):
        if gain is None:
            resp = yield self.query('ICUR?')
            returnValue(int(resp))
        else:
            yield self.write('ICUR ' + str(gain))
            resp = yield self.query('ICUR?')
            returnValue(int(resp))

    @inlineCallbacks
    def sig_lvl(self):
        resp = yield self.query('ILVL?')
        returnValue(int(resp))

    @inlineCallbacks
    def sine_out_amplitude(self,  amp = None):
        if amp is None:
            resp = yield self.query('SLVL?')
            returnValue(float(resp))
        else:
            yield self.write('SLVL ' + str(amp))
            resp = yield self.query('SLVL?')
            returnValue(float(resp))

    @inlineCallbacks
    def sine_offset(self,offset = None):
        if offset is None:
            resp = yield self.query('SOFF?')
            returnValue(float(resp))
        else:
            if float(offset) < -5 or float(offset) > 5:
                raise ValueError("Offset must be between -5 and +5")
            else:
                yield self.write('SOFF ' + str(offset))
                resp = yield self.query('SOFF?')
                returnValue(float(resp))

    @inlineCallbacks
    def sine_ref(self,  ref = None):
        if ref is None:
            resp = yield self.query('REFM?')
            returnValue(int(resp))
        else:
            yield self.write('REFM ' + str(ref))
            resp = yield self.query('REFM?')
            returnValue(int(resp))

    @inlineCallbacks
    def trigger_sign(self, sign = None):
        if sign is None:
            resp = yield self.query('RTRG?')
            returnValue(int(resp))
        else:
            yield self.write('RTRG ' + str(sign))
            resp = yield self.query('RTRG?')
            returnValue(int(resp))

    @inlineCallbacks
    def trigger_z(self, z_in = None):
        if z_in is None:
            resp = yield self.query('REFZ?')
            returnValue(int(resp))
        else:
            yield self.write('REFZ ' + str(z_in))
            resp = yield self.query('REFZ?')
            returnValue(int(resp))

    @inlineCallbacks
    def input_mode(self, mode = None):
        if mode is None:
            resp = yield self.query('IVMD?')
            returnValue(int(resp))
        else:
            yield self.write('IVMD ' + str(mode))
            resp = yield self.query('IVMD?')
            returnValue(int(resp))

    @inlineCallbacks
    def voltage_mode(self, mode = None):
        if mode is None:
            resp = yield self.query('ISRC?')
            returnValue(int(resp))
        else:
            yield self.write('ISRC ' + str(mode))
            resp = yield self.query('ISRC?')
            returnValue(int(resp))

    @inlineCallbacks
    def voltage_coupling(self, mode = None):
        if mode is None:
            resp = yield self.query('ICPL?')
            returnValue(int(resp))
        else:
            yield self.write('ICPL ' + str(mode))
            resp = yield self.query('ICPL?')
            returnValue(int(resp))

    @inlineCallbacks
    def input_rng(self, mode = None):
        if mode is None:
            resp = yield self.query('IRNG?')
            returnValue(int(resp))
        else:
            yield self.write('IRNG ' + str(mode))
            resp = yield self.query('IRNG?')
            returnValue(int(resp))

    @inlineCallbacks
    def aux_input(self, n):
        resp = yield self.query('OAUX? ' + str(n))
        returnValue(float(resp))

    @inlineCallbacks
    def aux_output(self, n, v = None):
        if v is None:
            resp = yield self.query('AUXV? ' + str(n))
            returnValue(float(resp))
        else:
            yield self.write('AUXV ' + str(n) + ', ' + str(v));
            returnValue(v)

    @inlineCallbacks
    def x(self):
        resp = yield self.query('OUTP? 0')
        returnValue(float(resp))

    @inlineCallbacks
    def y(self):
        resp = yield self.query('OUTP? 1')
        returnValue(float(resp))

    @inlineCallbacks
    def r(self):
        resp = yield self.query('OUTP? 2')
        returnValue(float(resp))

    @inlineCallbacks
    def theta(self):
        resp = yield self.query('OUTP? 3')
        returnValue(float(resp))

    @inlineCallbacks
    def xnoise(self):
        resp = yield self.query('OUTP? 8')
        returnValue(float(resp))

    @inlineCallbacks
    def ynoise(self):
        resp = yield self.query('OUTP? 9')
        returnValue(float(resp))

    @inlineCallbacks
    def get_xy(self):
        resp = yield self.query('SNAP? 0,1')
        returnValue(resp)

    @inlineCallbacks
    def get_rt(self):
        resp = yield self.query('SNAP? 2,3')
        returnValue(resp)

    @inlineCallbacks
    def autorange(self):
        resp = yield self.write('ARNG')
        returnValue(resp)

    @inlineCallbacks
    def autoscale(self):
        resp = yield self.write('ASCL')
        returnValue(resp)

    @inlineCallbacks
    def cout_xy_rt(self, chn, set = None):
        if set is None:
            resp = yield self.query('COUT? ' + str(chn))
            returnValue(resp)
        else:
            yield self.write('COUT ' + str(chn) + ',' + str(set))
            resp = yield self.query('COUT? ' + str(chn))
            returnValue(resp)

    @inlineCallbacks
    def cout_exp(self,axis, exp = None):
        if exp is None:
            resp = yield self.query('CEXP? ' + str(axis))
            returnValue(resp)
        else:
            yield self.write('CEXP ' + str(axis) + ',' + str(exp))
            resp = yield self.query('CEXP? ' + str(axis))
            returnValue(resp)

    @inlineCallbacks
    def time_constant(self, i=None):
        if i is None:
            resp = yield self.query("OFLT?")
            returnValue(getTC(int(resp)))
        else:
            yield self.write('OFLT ' + str(i))
            returnValue(getTC(i))

    @inlineCallbacks
    def sensitivity(self, i=None):
        if i is None:
            resp = yield self.query("SCAL?")
            returnValue(getSensitivity(int(resp)))
        else:
            yield self.write('SCAL ' + str(i))
            resp = yield self.query("SCAL?")
            returnValue(getSensitivity(int(resp)))

    # @inlineCallbacks
    # def auto_sensitivity(self):
    #     waittime = yield self.wait_time(c)
    #     r = yield self.r(c)
    #     sens = yield self.sensitivity(c)
    #     while r/sens > 0.95:
    #         #print "sensitivity up... ",
    #         yield self.sensitivity_up(c)
    #         yield util.wakeupCall(waittime)
    #         r = yield self.r(c)
    #         sens = yield self.sensitivity(c)
    #     while r/sens < 0.35:
    #         #print "sensitivity down... ",
    #         yield self.sensitivity_down(c)
    #         yield util.wakeupCall(waittime)
    #         r = yield self.r(c)
    #         sens = yield self.sensitivity(c)

    @inlineCallbacks
    def auto_gain(self):
        yield self.write("AGAN");
        #done = False
        resp = yield self.query("*STB? 1")
        while resp != '0':
            resp = yield self.query("*STB? 1")
            print("Waiting for auto gain to finish...")

    @inlineCallbacks
    def filter_slope(self, i=None):
        if i is None:
            resp = yield self.query("OFSL?")
            returnValue(int(resp))
        else:
            yield self.write('OFSL ' + str(i))
            returnValue(i)

    @inlineCallbacks
    def wait_time(self):
        tc = yield self.query("OFLT?")
        tc = getTC(int(tc))
        slope = yield self.query("OFSL?")
        slope = int(slope)
        if slope == 0:
            returnValue(5*tc)
        elif slope == 1:
            returnValue(7*tc)
        elif slope == 2:
            returnValue(9*tc)
        else:# slope == 3:
            returnValue(10*tc)


class sr860Server(GPIBManagedServer):
    name = 'sr860'
    deviceName = 'Stanford_Research_Systems SR860'
    deviceIdentFunc = 'identify_device'
    deviceWrapper = sr860Wrapper

    @setting(9988, server='s', address='s')
    def identify_device(self, c, server, address):
        print('identifying:', server, address)
        try:
            s = self.client[server]
            p = s.packet()
            p.address(address)
            p.write_termination('\r')
            p.read_termination('\r')
            p.write('*IDN?')
            p.read()
            p.write('*IDN?')
            p.read()
            ans = yield p.send()
            resp = ans.read[1]
            print('got ident response:', resp)
            if resp == 'Stanford_Research_Systems,SR860,003329,V1.47':
                returnValue(self.deviceName)
        except Exception as e:
            print('failed:', e)
            print('what what...')
            raise

    @setting(99, 'outputUnit', returns='?')
    def outputUnit(self, c):
        ''' returns a labrad unit, V or A, for what the main output type is. (R, X, Y) '''
        dev = self.selectedDevice(c)
        mode = yield dev.input_mode()
        if int(mode) == 0:
            returnValue(units.V)
        elif int(mode) == 1:
            returnValue(units.A)

    @setting(101, 'tb_Mode', mode='i', returns='i')
    def tb_mode(self, c, mode = None):
        ''' sets/gets the timebase mode (auto = 0 ; internal = 1) '''
        dev = self.selectedDevice(c)
        if mode is None:
            resp = yield dev.tbmode()
            returnValue(int(resp))
        else:
            resp = yield dev.tbmode(mode)
            returnValue(int(resp))

    @setting(102, 'freq_ext', returns='v')
    def freqext(self, c):
        ''' gets the external refernce frequncy '''
        dev = self.selectedDevice(c)
        resp = yield  dev.freqext()
        returnValue(float(resp))

    @setting(103, 'Phase', ph=[': query phase offset',  'v: set phase offset'], returns='v')
    def phase(self, c, ph = None):
        ''' sets/gets the phase offset to a value in degrees
        '''
        dev = self.selectedDevice(c)
        if ph is None:
            resp = yield dev.phase()
            returnValue(float(resp))
        else:
            resp = yield dev.phase(ph)
            returnValue(float(resp))
    @setting(104, 'Reference', ref=[': query reference source', 'i: set external (0) or internal (1) reference source'], returns='i')
    def reference(self, c, ref = None):
        """
		sets/gets the reference source. (internal source = 0 ; external source = 1 ; dual = 2 ; chop = 3)
		"""
        dev = self.selectedDevice(c)
        if ref is None:
            resp = yield dev.reference()
            returnValue(int(resp))
        else:
            resp = yield dev.reference(ref)
            returnValue(int(resp))

    @setting(105, 'Frequency', f=[': query frequency', 'v: set frequency'], returns='v')
    def frequency(self, c, f = None):
        """ Sets/gets the frequency of the internal reference. """
        dev = self.selectedDevice(c)
        if f is None:
            resp = yield dev.frequency()
            returnValue(float(resp))
        else:
            resp = yield dev.frequency(f)
            returnValue(float(resp))

    @setting(106, 'external_reference_slope', ers=[': query', 'i: set'], returns='i')
    def external_reference_slope(self, c, ers = None):
        """
        Get/set the external reference slope.
        0 = Sine, 1 = TTL Rising, 2 = TTL Falling
        """
        dev = self.selectedDevice(c)
        if ers is None:
            resp = yield dev.external_reference_slope()
            returnValue(int(resp))
        else:
            resp = yield dev.external_reference_slope(ers)
            returnValue(resp)

    @setting(107, 'Harmonic', h=[': query harmonic', 'i: set harmonic'], returns='i')
    def harmonic(self, c, h = None):
        """
        Get/set the harmonic.
        Harmonic can be set as high as 19999 but is capped at a frequency of 102kHz.
        """
        dev = self.selectedDevice(c)
        if h is None:
            resp = yield dev.harmonic()
            returnValue(int(resp))
        else:
            resp = yield dev.harmonic(h)
            returnValue(resp)

    @setting(108, 'sine_out_amplitude', amp=[': query', 'v: set'], returns='v')
    def sine_out_amplitude(self, c, amp = None):
        """
        Set/get the amplitude of the sine out.
        Accepts values between .004 and 5.0 V.
        """
        dev = self.selectedDevice(c)
        if amp is None:
            resp = yield dev.sine_out_amplitude()
            returnValue(float(resp))
        else:

            resp = yield dev.sine_out_amplitude(amp)
            returnValue(float(resp))

    @setting(109, 'Sine Offset', offset = 'v', returns='v')
    def sine_offset(self, c, offset = None):
        '''
        gets/sets the sine out dc offset level in volts, can be programmed from -5.00 to +5.00 volts
        '''
        dev = self.selectedDevice(c)

        if offset is None:
            resp = yield dev.sine_offset()
            returnValue(float(resp))
        else:
            if float(offset) < -5 or float(offset) > 5:
                raise ValueError("Offset must be between -5 and +5")
            else:

                resp = yield dev.sine_offset(offset)
                returnValue(float(resp))

    @setting(110, 'Sine ref', ref = 'i', returns='i')
    def sine_ref(self, c, ref = None):
        ''' gets/sets the sine output refernce mode (common = 0 ; differential = 1)
        '''
        dev = self.selectedDevice(c)
        if ref is None:
            resp = yield dev.sine_ref()
            returnValue(int(resp))
        else:

            resp = yield dev.sine_ref(ref)
            returnValue(int(resp))

    @setting(111, 'Trigger Sign', sign = 'i', returns='i')
    def trigger_sign(self, c, sign = None):
        '''
        gets/sets the external refernce trigger mode (sine = 0 ; positive TLL = 1 ; negative TLL = 2)
        '''
        dev = self.selectedDevice(c)
        if sign is None:
            resp = yield dev.trigger_sign()
            returnValue(int(resp))
        else:

            resp = yield dev.trigger_sign(sign)
            returnValue(int(resp))

    @setting(112, 'Trigger Z', z_in = 'i', returns='i')
    def trigger_z(self, c, z_in = None):
        ''' gets/sets the external refernce trigger input impedance (50Ohm = 0 ; 1MOhm = 1 )
        '''
        dev = self.selectedDevice(c)
        if z_in is None:
            resp = yield dev.trigger_z()
            returnValue(int(resp))
        else:

            resp = yield dev.trigger_z(z_in)
            returnValue(int(resp))

    @setting(113, 'iv_input_mode', mode = 'i', returns='i')
    def iv_input_mode(self, c, mode = None):
        ''' gets/sets the signal input to voltage (0) or current (1)
        '''
        dev = self.selectedDevice(c)
        if mode is None:
            resp = yield dev.input_mode()
            returnValue(int(resp))
        else:
            resp = yield dev.input_mode(mode)
            returnValue(int(resp))

    @setting(114, 'Voltage Input Mode', mode = 'i', returns='i')
    def voltage_mode(self, c, mode = None):
        ''' gets/sets the signal input to voltage mode to A (0) or A - B (1)
        '''
        dev = self.selectedDevice(c)
        if mode is None:
            resp = yield dev.voltage_mode()
            returnValue(int(resp))
        else:
            resp = yield dev.voltage_mode(mode)
            returnValue(int(resp))

    @setting(115, 'voltage_coupling', mode = 'i', returns='i')
    def voltage_coupling(self, c, mode = None):
        ''' gets/sets the signal input to voltage coupling mode to AC (0) or DC (1)
        '''
        dev = self.selectedDevice(c)
        if mode is None:
            resp = yield dev.voltage_coupling()
            returnValue(int(resp))
        else:
            resp = yield dev.voltage_coupling(mode)
            returnValue(int(resp))

    @setting(116, 'input_rng', mode = 'i', returns='i')
    def input_rng(self, c, mode = None):
        ''' gets/sets the signal input to voltage range to 1V (0), 300mV (1), 100mV (2), 30mV (3), or 10mV (4)
        '''
        dev = self.selectedDevice(c)
        if mode is None:
            resp = yield dev.input_rng()
            returnValue(int(resp))
        else:
            resp = yield dev.input_rng(mode)
            returnValue(int(resp))

    @setting(117, 'Aux Input', n='i', returns='v')
    def aux_input(self, c, n):
        """Query the value of Aux Input n (1,2,3,4)"""
        dev = self.selectedDevice(c)
        if int(n) < 1 or int(n) > 4:
            raise ValueError("n must be 1,2,3, or 4!")
        else:
            n = int(n) - 1
        resp = yield dev.aux_input(n)
        returnValue(float(resp))

    @setting(118, 'Aux Output', n='i', v=['v'], returns='v')
    def aux_output(self, c, n, v = None):
        """Get/set the value of Aux Output n (1,2,3,4). v can be from -10.5 to 10.5 V."""
        dev = self.selectedDevice(c)
        if int(n) < 1 or int(n) > 4:
            raise ValueError("n must be 1,2,3, or 4!")
        else:
            n = int(n) - 1
        if v is None:
            resp = yield dev.aux_output(n)
            returnValue(float(resp))
        else:
            resp = yield dev.aux_output(n, v);
            returnValue(resp)

    @setting(119, 'x', returns='v')
    def x(self, c):
        """Query the value of X"""
        dev = self.selectedDevice(c)
        resp = yield dev.x()
        returnValue(float(resp))

    @setting(120, 'y', returns='v')
    def y(self, c):
        """Query the value of Y"""
        dev = self.selectedDevice(c)
        resp = yield dev.y()
        returnValue(float(resp))

    @setting(121, 'r', returns='v')
    def r(self, c):
        """Query the value of R"""
        dev = self.selectedDevice(c)
        resp = yield dev.r()
        returnValue(float(resp))

    @setting(122, 'theta', returns='v')
    def theta(self, c):
        """Query the value of theta """
        dev = self.selectedDevice(c)
        resp = yield dev.theta()
        returnValue(float(resp))

    @setting(123, 'XNoise', returns='v')
    def xnoise(self, c):
        """Query the value of the voltage noise in X """
        dev = self.selectedDevice(c)
        resp = yield dev.xnoise()
        returnValue(float(resp))

    @setting(124, 'YNoise', returns='v')
    def ynoise(self, c):
        """Query the value of the voltage noise in Y """
        dev = self.selectedDevice(c)
        resp = yield dev.ynoise()
        returnValue(float(resp))
    @setting(125, 'Autorange')
    def autorange(self, c):
        """Autoranges the device """
        dev = self.selectedDevice(c)
        yield dev.autorange()
    @setting(126, 'Autoscale')
    def autoscale(self, c):
        """Autoscales the device, automatically adjusts the sensitivity """
        dev = self.selectedDevice(c)
        yield dev.autoscale()


    @setting(127, 'cout_xy_rt', chn = 'i', set = 'i', returns = 'i')
    def cout_xy_rt(self, c, chn, set = None):
        """Sets/gets the output setting for a given output (X/Y = 0; RTheta = 1). For example cout_xy_rt(1,1) sets channel 1 output to r/theta."""
        dev = self.selectedDevice(c)
        if set is None:
            resp = yield dev.cout_xy_rt(chn)
            returnValue(int(resp))
        else:
            resp = yield dev.cout_xy_rt(chn,set)
            returnValue(int(resp))

    @setting(128, 'cout_exp', axis = 'i', exp = 'i', returns = 'i')
    def cout_exp(self, c, axis, exp = None):
        """Sets/gets the output expand for an output axis (X = 0 ; Y = 1; R = 2). For example cout_xy_rt(1,1) sets channel 1 output to r/theta."""
        dev = self.selectedDevice(c)
        if exp is None:
            resp = yield dev.cout_exp(axis)
            returnValue(int(resp))
        else:

            resp = yield dev.cout_exp(axis, exp)
            returnValue(int(resp))

    @setting(129, 'Time Constant', tc='v', returns='v')
    def time_constant(self, c, tc=None):
        """ Set/get the time constant. i=0 --> 1 us; 1-->3us, 2-->10us, 3-->30us, ..., 21 --> 30ks """
        dev = self.selectedDevice(c)
        if tc is None:
            resp = yield dev.query("OFLT?")
            returnValue(getTC(int(resp)))
        else:
            tc = getTCInt(tc)
            yield dev.write('OFLT {}'.format(tc))
            resp = yield dev.query("OFLT?")
            returnValue(getTC(int(resp)))

    @setting(130, 'Sensitivity', i='v', returns='v')
    def sensitivity(self, c, i=None):
        """ Set/get the sensitivity. To set the sensitivity, input the voltage sensitivity in Volts or the current sensitivity in Amps.

        Lookup table in the manual: i=27 --> 1 nV/fA; 26-->5nV/fA, 25-->10nV/fA, 24-->20nV/fA, ..., 0 --> 1V/uA
        """
        dev = self.selectedDevice(c)
        iv_mode = yield dev.input_mode()
        if int(iv_mode) == 0:
            u = units.V
        elif int(iv_mode) == 1:
            u = units.A
        else:
            u = 'none'
        if i is None:
            resp = yield dev.sensitivity()
            if u != 'none':
                returnValue(resp * u)
            else:
                returnValue(resp)
        else:
            jj = getSensitivityInt(i, int(iv_mode))
            resp = yield dev.sensitivity(jj)
            if u != 'none':
                returnValue(resp * u)
            else:
                returnValue(resp)

    @setting(131, 'Filter Slope', i='i', returns='i')
    def filter_slope(self, c, i=None):
        '''
        Sets/gets the low pass filter slope. 0=>6, 1=>12, 2=>18, 3=>24 dB/oct
        '''
        dev = self.selectedDevice(c)
        if i is None:
            resp = yield dev.filter_slope()
            returnValue(resp)
        else:
            resp = yield dev.filter_slope(i)
            returnValue(resp)

    @setting(132, 'Get XY', returns='*v')
    def get_xy(self, c):
        """Query the value of the X and Y outputs simultaneously """
        dev = self.selectedDevice(c)
        resp = yield dev.get_xy()
        ans = [resp.split(',')[0], resp.split(',')[1]]
        returnValue(ans)

    @setting(133, 'get_rt', returns='*v')
    def get_rt(self, c):
        """Query the value of the R and Theta outputs simultaneously """
        dev = self.selectedDevice(c)
        resp = yield dev.get_rt()
        ans = [resp.split(',')[0], resp.split(',')[1]]
        returnValue(ans)

    @setting(134, 'gnd_mode', mode='i', returns='i')
    def gnd_mode(self, c, mode = None):
        '''
        Sets/gets voltage input shield grounding setting (grounded = 1 ; floating = 0)
        '''
        dev = self.selectedDevice(c)
        if mode is None:
            resp = yield dev.gnd_mode()
            returnValue(resp)
        else:
            resp = yield dev.gnd_mode(mode)
            returnValue(resp)

    @setting(135, 'sig_lvl', returns='i')
    def sig_lvl(self, c):
        '''
        Queries the signal strength and returns an integer from 0 (low signal strength) to 4 (overload)
        '''
        dev = self.selectedDevice(c)
        resp = yield dev.sig_lvl()
        returnValue(resp)

    @setting(136, 'curr_gain', gain='i', returns='i')
    def curr_gain(self, c, gain=None):
        '''
        Sets/gets intput current gain (0 = 1MOhm [1uA] ; 1 = 100MOhm [10nA])
        '''
        dev = self.selectedDevice(c)
        if gain is None:
            resp = yield dev.curr_gain()
            returnValue(resp)
        else:
            resp = yield dev.curr_gain(gain)
            returnValue(resp)

    @setting(137, 'sensitivity_up', returns='v')
    def sensitivity_up(self, c):
        """ Increases the sensitivity one increment
		"""
        dev = self.selectedDevice(c)
        sens = yield dev.query('SCAL?')
        if int(sens) < 27 and int(sens) >= 0:
            yield dev.write(int(sens) + 1)
        else:
            pass
        resp = yield dev.query('SCAL?')
        returnValue(getSensitivity(resp))

    @setting(138, 'sensitivity_down', returns='v')
    def sensitivity_down(self, c):
        """ Decreases the sensitivity one increment
		"""
        dev = self.selectedDevice(c)
        sens = yield dev.query('SCAL?')
        if int(sens) <= 27 and int(sens) > 0:
            yield dev.write(int(sens) - 1)
        else:
            pass
        resp = yield dev.query('SCAL?')
        returnValue(getSensitivity(resp))




__server__ = sr860Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
