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
# Modified by Sasha Zibrov 2017
"""
### BEGIN NODE INFO
[info]
name = SR830
version = 2.9.1
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
from numpy import log2
from labrad.server import setting
from labrad.gpib import GPIBManagedServer
from twisted.internet.defer import inlineCallbacks, returnValue
from struct import unpack

def getTC(i):
    """converts from the integer label used by the SR830 to a time in sec"""
    if i < 0:
        return getTC(0)
    elif i > 19:
        return getTC(19)
    elif i % 2 == 0:
        return 10**(-5 + i/2)
    else:
        return 3*10**(-5 + i/2)

def getSensitivity(i, mode):
    """converts form the integer label used by the SR830 to a sensitivity based on the mode"""
    if i < 0:
        return getSensitivity(0, mode)
    elif i > 26:
        return getSensitivity(26, mode)
    elif i % 3 == 0:
        if mode == 0 or mode == 1:
            return 2 * 10**(-9 + i//3)
        else:
            return 2 * 10**(-15 + i//3)
    elif i % 3 == 1:
        if mode == 0 or mode == 1:
            return 5 * 10**(-9 + i//3)
        else:
            return 5 * 10**(-15 + i//3)
    else:
        if mode == 0 or mode == 1:
            return 10 * 10**(-9 + i//3)
        else:
            return 10 * 10**(-15 + i//3)
    

MODE_DICT = {
    'A': 0,
    'A-B': 1,
    '1M': 2,
    '100M': 3
}

def getSensitivityInt(v, mode):
    ''' converty from real sensitivity to an integer value taken by the sr830'''
    if (mode == 0 or mode == 1): #Voltage
        sens = int(round(3*log10(v)))+26
    else: #Current
        sens = int(round(3*log10(v)))+44
    return sens

def getTCInt(t):
    ''' convert from real time constant values to an integer value taken by the sr830'''
    timeconstant = int(round(2*log10(t)))+10
    return timeconstant


class SR830(GPIBManagedServer):
    name = 'SR830'
    deviceName = 'Stanford_Research_Systems SR830'

    @setting(11, 'Input Mode', mode='s', returns='i')
    def input_mode(self, c, mode=None):
        """returns the input mode. 0=A, 1=A-B, 2=I(10**6), 3=I(10**8)"""
        dev = self.selectedDevice(c)
        if mode is not None:
            if mode.upper() in list(MODE_DICT.keys()):
                mode = MODE_DICT[mode.upper()]
            if mode not in [0, 1, 2, 3]:
                raise Exception('Error, mode must be in [0, 1, 2, 3, A, A-B,'
                                ' 1M, 100M], requested: {}'.format(mode))
            yield dev.write('ISRC {}'.format(mode))
        mode = yield dev.query('ISRC?')
        returnValue(int(mode))

    @setting(12, 'Phase', ph=['', 'v'], returns='v: phase')
    def phase(self, c, ph=None):
        """Set or get the excitation phase offset.

        Args:
            ph (Value[deg]): Phase offset to set. If not included, then we
                query the existing phase instead.

        Returns:
            (Value[deg]): The phase offset.
        """
        dev = self.selectedDevice(c)
        if ph is not None:
            yield dev.write('PHAS {}'.format(ph))
        resp = yield dev.query('PHAS?')
        returnValue(float(resp))

    @setting(13, 'Reference',
             ref=[': query reference source', 'b: set external (false) or internal (true) reference source'],
             returns='b')
    def reference(self, c, ref=None):
        """Set or get the reference source.

        Args:
            ref (bool): False sets external source, True sets internal source.
                If the argument is omitted we query the existing source.

        Returns:
            (bool):  The excitation source.
        """
        dev = self.selectedDevice(c)
        if ref is not None:
            yield dev.write('FMOD {}'.format(int(ref)))
        resp = yield dev.query('FMOD?')
        returnValue(bool(int(resp)))

    @setting(14, 'Frequency', f=[': query frequency', 'v: set frequency'], returns='v')
    def frequency(self, c, f=None):
        """Set or get the excitation frequency (when source is internal)

        Args:
            f (value): Frequency to set.  If none, then we query the
                existing frequency

        Returns:
            (value[Hz]): The internal excitation frequency.
        """
        dev = self.selectedDevice(c)
        if f is not None:
            yield dev.write('FREQ {}'.format(f))
        resp = yield dev.query('FREQ?')
        returnValue(float(resp))

    @setting(15, 'External Reference Slope', ers=[': query', 'i: set'], returns='i')
    def external_reference_slope(self, c, ers=None):
        """Set or get the external reference slope.

        Args:
            ers (int): Specifies the external reference source.
                0 = Sine, 1 = TTL Rising, 2 = TTL Falling

        Returns:
            (int):  The external reference source.
                0 = Sine, 1 = TTL Rising, 2 = TTL Falling
        """
        dev = self.selectedDevice(c)
        if ers is not None:
            yield dev.write('RSLP {}'.format(ers))
        resp = yield dev.query('RSLP?')
        returnValue(int(resp))

    @setting(16, 'Harmonic', h=[': query harmonic', 'i: set harmonic'], returns='i')
    def harmonic(self, c, h=None):
        """Set or get the harmonic.

        Harmonic can be set as high as 19999 but is capped at a frequency of
            102kHz.

        Args:
            h (int): The harmonic to set.  Integer from 1 to 19999, but frequency
                must be less than 102kHz (that is, harmonic * f0).

        Returns:
            (int): The harmonic being measured.
        """
        dev = self.selectedDevice(c)
        if h is not None:
            yield dev.write('HARM {}'.format(h))
        resp = yield dev.query('HARM?')
        returnValue(int(resp))

    @setting(17, 'Sine Out Amplitude', amp=[': query', 'v: set'], returns='v')
    def sine_out_amplitude(self, c, amp=None):
        """ Set or get the amplitude of the excitation sine waveform.

        Args:
            amp (Value): RMS excitation amplitude
                Accepts values between .004 and 5.0 Vrms.  This will be
                coerced to the nearest 0.002 Vrms.

        Returns:
            (Value[V]): The RMS excitation amplitude.
        """
        dev = self.selectedDevice(c)
        if amp is not None:
            yield dev.write('SLVL {}'.format(amp))
        resp = yield dev.query('SLVL?')
        returnValue(float(resp))

    @setting(18, 'Aux Input', n='i', returns='v')
    def aux_input(self, c, n):
        """Get the value of the Aux Input channel n (1,2,3,4)

        Args:
            n (i): Aux input channel to query.

        Returns:
            (Value[V]): the value of the specified Aux input.
        """
        dev = self.selectedDevice(c)
        if int(n) < 1 or int(n) > 4:
            raise ValueError("n must be 1,2,3, or 4!")
        resp = yield dev.query('OAUX? {}'.format(n))
        returnValue(float(resp))

    @setting(19, 'Aux Output', n='i', v=['v'], returns='v')
    def aux_output(self, c, n, v=None):
        """Get or set the value of an Aux Output.

        Args:
            n (i): The aux input channel to set or query. n (1,2,3,4).
            v (Value[V]):  The value to set the specified Aux channel to.
                v can be from -10.5 to 10.5 V.

        Returns:
            (Value[V]): The voltage of Aux channel n.
        """
        dev = self.selectedDevice(c)
        if int(n) < 1 or int(n) > 4:
            raise ValueError("n must be 1,2,3, or 4!")
        if v is not None:
            yield dev.write('AUXV {}, {}'.format(n, v))
        resp = yield dev.query('AUXV? {}'.format(n))
        returnValue(float(resp))

    @setting(21, 'x', returns='v')
    def x(self, c):
        """Query the value of X, the in phase signal.

        Returns:
            (Value[V] or [A]): The X reading in units dependent on the input
                mode.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('OUTP? 1')
        returnValue(float(resp))

    @setting(22, 'y', returns='v')
    def y(self, c):
        """Query the value of Y, the quadrature signal.

        Returns:
            (Value[V] or [A]): The Y reading in units dependent on the input
                mode.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('OUTP? 2')
        returnValue(float(resp))

    @setting(23, 'r', returns='v')
    def r(self, c):
        """Query the value of R, the magnitude of the signal.

        Returns:
            (Value[V] or [A]): The R reading in units dependent on the input
                mode.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('OUTP? 3')
        returnValue(float(resp) )

    @setting(24, 'theta', returns='v')
    def theta(self, c):
        """Query the value of theta: arctan(quadrature-signal/in-phase-signal).

        Returns:
            (Value): The value of theta.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query('OUTP? 4')
        returnValue(float(resp))

    @setting(30, 'Time Constant', tc='v', returns='v')
    def time_constant(self, c, tc=None):
        """Set or get the time constant.

        Args:
            i (i): The time constant to set.
                i=0 --> 10 us; 1-->30us, 2-->100us, 3-->300us, ..., 19 --> 30ks

        Returns:
            (Value[s]): The time constant.

        """
        dev = self.selectedDevice(c)
        if tc is not None:
            tc = getTCInt(tc)
            yield dev.write('OFLT {}'.format(tc))
        resp = yield dev.query("OFLT?")
        returnValue(getTC(int(resp)))

    @setting(31, 'Sensitivity', sens='v', returns='v')
    def sensitivity(self, c, sens=None):
        """Set or get the sensitivity.

        Args:
            no input: return the current sensitivity without unit
            input: set the current sensitivity and return the set sensitivity without unit

        Returns:
            (Value or ):  The input range (sensitivity).
        """
        dev = self.selectedDevice(c)
        mode = yield self.input_mode(c)
        if sens is not None:
            sens = getSensitivityInt(sens, mode)
            yield dev.write('SENS {}'.format(sens))
        resp = yield dev.query("SENS?")
        returnValue(getSensitivity(int(resp), mode))

    @setting(41, 'Sensitivity Up', returns='v')
    def sensitivity_up(self, c):
        """Kicks the sensitivity up a notch."""
        dev = self.selectedDevice(c)
        sens = yield dev.query("SENS?")
        sens = getSensitivity(int(sens)+1)
        sens = yield self.sensitivity(c, sens)
        returnValue(sens)

    @setting(42, 'Sensitivity Down', returns='v')
    def sensitivity_down(self, c):
        """Turns the sensitivity down a notch."""
        dev = self.selectedDevice(c)
        sens = yield dev.query("SENS?")
        sens = getSensitivity(int(sens)-1)
        sens = yield self.sensitivity(c, sens)
        returnValue(sens)

    @setting(43, 'Auto Sensitivity')
    def auto_sensitivity(self, c):
        """Automatically adjusts sensitivity until signal is between 35% and 95% of full range."""
        waittime = yield self.wait_time(c)
        r = yield self.r(c)
        sens = yield self.sensitivity(c)
        mode = yield self.input_mode(c)
        previousSens = sens

        while r == 0:
            sens = getSensitivity(getSensitivityInt(sens, mode)-5)
            sens = yield self.sensitivity(c, sens)
            r = yield self.r(c)

        if r/sens < 0.35:
            sens = getSensitivity(getSensitivityInt(r/0.35, mode))
            sens = yield self.sensitivity(c, sens)
            r = yield self.r(c)

        while r/sens > 0.35:
            yield self.sensitivity_up(c)
            yield util.wakeupCall(waittime)
            r = yield self.r(c)
            sens = yield self.sensitivity(c)
            if (sens == previousSens) and (r/sens<=1):
                break
            else:
                previousSens = sens

    @setting(32, 'Auto Gain')
    def auto_gain(self, c):
        """Runs the auto gain function. Does nothing if time constant >= 1s."""
        dev = self.selectedDevice(c)
        yield dev.write("AGAN");
        done = False
        resp = yield dev.query("*STB? 1")
        while resp != '0':
            resp = yield dev.query("*STB? 1")
            print("Waiting for auto gain to finish...")

    @setting(33, 'Filter Slope', i='i', returns='i')
    def filter_slope(self, c, i=None):
        """Sets/gets the low pass filter slope. 0=>6, 1=>12, 2=>18, 3=>24 dB/oct"""
        dev = self.selectedDevice(c)
        if i is None:
            resp = yield dev.query("OFSL?")
            returnValue(int(resp))
        else:
            yield dev.write('OFSL {}'.format(i))
            returnValue(i)

    @setting(34, 'Wait Time', returns='v')
    def wait_time(self, c):
        """Returns the recommended wait time given current time constant and low-pass filter slope."""
        dev = self.selectedDevice(c)
        tc = yield dev.query("OFLT?")
        tc = getTC(int(tc))
        slope = yield dev.query("OFSL?")
        slope = int(slope)
        if slope == 0:
            returnValue(5*tc) # recommended 5
        elif slope == 1:
            returnValue(7*tc) # 7
        elif slope == 2:
            returnValue(9*tc)
        else:# slope == 3:
            returnValue(10*tc) # 10 etc.

    @setting(35, 'Output Overload', returns='b')
    def output_overload(self, c):
        """Gets the output overload status bit

        The output overload status bit will return True if the input voltages
        has exceeded the 'sensitivity' setting since the last time the status
        bits were read or cleared.  Reading this status bit or sending a *CLS
        command will reset the value of this status bit to False until another
        overload event occurs.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query("LIAS? 2")
        returnValue(bool(int(resp)))

    @setting(36, 'Input Overload', returns='b')
    def input_overload(self, c):
        """Gets the input overload status bit

        The input overload status bit will return True if voltage inputs are
        greater than 1.4Vpk (unless removed by AC coupling) or current inputs
        greater than 10 uA DC or 1.4 uA AC (1MOhm gain) or 100 nA DC or 14 nA AC
        (100MW gain). Reduce the input signal level.
        """
        dev = self.selectedDevice(c)
        resp = yield dev.query("LIAS? 2")
        returnValue(bool(int(resp)))

    @setting(99, 'Input Ground', gnd='i', returns='i')
    def input_ground(self, c, gnd=None):
        """Get or sets the input shield ground configuration.

        Args:
            gnd (int):  0: float; 1: ground
        Returns:
            (int):  The input shield ground status after setting (if requested).
        """
        dev = self.selectedDevice(c)
        if gnd is not None:
            gnd = int(gnd)
            if gnd not in [0, 1]:
                raise Exception('Error, requested input shield ground {}. '
                                'Please select "0" for float or "1" for ground.'
                                ''.format(gnd))
            yield dev.write("IGND {}".format(gnd))
        resp = yield dev.query("IGND?")
        returnValue(int(resp))


    @setting(37, 'Input Coupling', coupling='s', returns='i')
    def input_coupling(self, c, coupling=None):
        """Get or sets the input coupling.

        Args:
            coupling:  0: AC or 1: DC
        Returns:
            (int):  The input coupling after setting (if requested).
        """
        coupling_dict = {
            'AC': 0,
            'DC': 1
        }
        dev = self.selectedDevice(c)
        if coupling is not None:
            if isinstance(coupling, str):
                coupling = coupling.upper()
                if coupling not in (list(coupling_dict.keys()) + [0, 1]):
                    raise Exception('Error: Requested {} inpout coupling. Please'
                                    ' select from {},'.format(coupling,
                                                              coupling_dict))
                coupling = coupling_dict[coupling]
            yield dev.write("ICPL {}".format(coupling))
        resp = yield dev.query("ICPL?")
        returnValue(int(resp))

    @setting(38, 'Notch Filter', mode='i', returns='i')
    def notch_filter(self, c, mode=None):
        """Get or sets the input notch filter: [none, line, line 2x].

        Args:
            mode:  0: none, 1: line, 2: 2x: line
        Returns:
            (int):  The input notch filter after setting (if requested).
        """
        dev = self.selectedDevice(c)
        if mode is not None:
            mode = int(mode)
            if mode not in [0,1,2]:
                raise Exception('Error: Requested {}.  Please choose either:'
                                '0: No filter; 1: Line; or 2: 2x Line.'
                                ''.format(mode))
            yield dev.write("ILIN {}".format(mode))
        resp = yield dev.query("ILIN?")
        returnValue(int(resp))


    @setting(39, 'Reserve Mode', mode='i', returns='i')
    def reserve_mode(self, c, mode=None):
        """Get or sets the reserve mode.

        Args:
            mode:  0: High Reserve, 1: Normal, 2: Low Noise
        Returns:
            (int):  The reserve mode after setting (if requested).
        """
        dev = self.selectedDevice(c)
        if mode is not None:
            mode = int(mode)
            if mode not in [0, 1, 2]:
                raise Exception('Error: Requested {}.  Please choose either:'
                                '0: high reserve; 1: normal; 2: low noise.'
                                ''.format(mode))
            yield dev.write("RMOD {}".format(mode))
        resp = yield dev.query("RMOD?")
        returnValue(int(resp))


    @setting(40, 'Sync Filter', mode='i', returns = 'i')
    def sync_filter(self, c, mode=None):
        """Get or sets the sync filter status.

        Args:
            mode:  0: off, 1: on; active only if detection frequency
                (= reference * harmonic) is less than 200 Hz.
        Returns:
            (int):  The sync filter status after setting (if requested).
        """
        dev = self.selectedDevice(c)
        if mode is not None:
            mode = int(mode)
            if mode not in [0, 1]:
                raise Exception('Error: Requested {}. 0: off or 1: '
                                'on'.format(mode))
            yield dev.write("SYNC {}".format(mode))
        resp = yield dev.query("SYNC?")
        returnValue(int(resp))

    @setting(101, 'Sample Rate', rate = 'v', returns = 'v')
    def sample_rate(self, c, rate = None):
        '''Sets the sampling rate for buffered data acquisition. Only discrete values are accepted of 
        0.0625 Hz, 0.125 Hz, 0.250 Hz, 0.5 Hz, 1 Hz, 2 Hz, 4 Hz, 8 Hz, 16 Hz, 32 Hz, 64 Hz, 128 Hz, 256 Hz,
        and 512 Hz. The function will round to the nearest frequency.'''
        dev = self.selectedDevice(c)
        if rate is not None:
            index = int(round(log2(rate/0.0625)))
            if index < 0:
                index = 0
            elif index > 13:
                index = 13
            yield dev.write("SRAT {}".format(index))
        resp = yield dev.query("SRAT?")
        freq = 0.0625*2**int(resp)
        returnValue(freq)
        
    @setting(102, 'Buffer Mode', mode = 'i', returns = 'i')
    def buffer_mode(self, c, mode = None):
        '''Sets the buffer mode for buffered data acquisition. 0 corresponds to 1 shot (stops after the buffer
        is filled) and 1 corresponds to loop (overwrites earlier values in the buffer if it's filled).'''
        dev = self.selectedDevice(c)
        if mode is not None:
            yield dev.write("SEND {}".format(mode))
            
        resp = yield dev.query("SEND?")
        returnValue(int(resp))
        
    @setting(103, 'Clear Buffer')
    def clear_buffer(self, c):
        dev = self.selectedDevice(c)
        yield dev.write("REST")
        
    @setting(104, 'Pause Buffer')
    def pause_buffer(self, c):
        dev = self.selectedDevice(c)
        yield dev.write("PAUS")
        
    @setting(105, 'Start Buffer')
    def start_buffer(self, c):
        dev = self.selectedDevice(c)
        yield dev.write("STRT")

    @setting(106, 'Buffer Points', returns = 'i')
    def buffer_points(self, c):
        dev = self.selectedDevice(c)
        resp = yield dev.query('SPTS?')
        returnValue(int(resp))

    @setting(107, 'Read Buffer', chnl_ind = 'i', start_bin = 'i', num_points = 'i', returns = '*v')
    def read_buffer(self, c, chnl_ind, start_bin, num_points):
        '''Read values in the buffer specified by the channel index. Returns values from the start_bin
        until the number of points desired. Throws an error if too many points are attempted to be collected.'''
        dev = self.selectedDevice(c)
        data = yield dev.query('TRCB? ' + str(chnl_ind) +', '  + str(start_bin) +', '  + str(num_points))
        length = len(data)
        data = [unpack('f',data[i:i+4])[0] for i in range(0,length,4)]
        returnValue(data)

__server__ = SR830()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)


"""Not implemented commands:

RSPL (?) {i}: set or query reference trigger (external only)

"""
