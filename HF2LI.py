# Copyright []
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
name = HF2LI Server
version = 1.0
description = Communicates with the Lock in, which has built in PLL / PID methods.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

#TODO: Filter BW, Filter Order, and Harmonic info for PID control
#TODO: reprogram as a proper device server to make it be able to host connections to several HF2LI at the same time

from labrad.server import LabradServer, setting
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor, defer
import labrad.units as units
from labrad.types import Value
import time
import numpy as np
import zhinst
import zhinst.utils
import sys


class HF2LIServer(LabradServer):
    name = "HF2LI Server"    # Will be labrad name of server

#------------------------------------------------------------------------------------------------------------------------------------------#
    """
    The following section of code has initializing and general lock in commands that can be useful in multiple contexts.
    """

    def initServer(self):  # Do initialization here
        self.daq = None
        self.dev_ID = 'No Device Selected'
        self.device_list = []
        self.props = None
        self.sweeper = None
        self.pidAdvisor = None
        self.poll_data = None
        print("Server initialization complete")

    @inlineCallbacks
    def initPIDAdvisor(self, c = None):
        self.pidAdvisor = yield self.daq.pidAdvisor()
        #Set device
        yield self.pidAdvisor.set('pidAdvisor/device', self.dev_ID)
        #Automatic response calculation triggered by parameter change.
        yield self.pidAdvisor.set('pidAdvisor/auto', 1)
        #Adjusts the demodulator bandwidth to fit best to the specified target bandwidth of the full system.
        yield self.pidAdvisor.set('pidAdvisor/pid/autobw', 1)
        # DUT model
        # source = 4: Internal PLL
        yield self.pidAdvisor.set('pidAdvisor/dut/source', 4)
        # IO Delay of the feedback system describing the earliest response
        # for a step change. This parameter does not affect the shape of
        # the DUT transfer function
        yield self.pidAdvisor.set('pidAdvisor/dut/delay', 0.0)

    @inlineCallbacks
    def initSweeper(self, c = None):
        self.sweeper  = yield self.daq.sweep()
        yield self.sweeper.set('sweep/device', self.dev_ID)

    @setting(100,returns = '')
    def detect_devices(self,c):
        """ Attempt to connect to the LabOne server (not a LadRAD server) and get a list of devices."""
        try:
            self.daq = yield zhinst.utils.autoConnect()
            print('LabOne DAQ Server detected.')
            self.device_list = yield zhinst.utils.devices(self.daq)
            print('Devices connected to LabOne DAQ Server are the following:')
            print(self.device_list)
        except RuntimeError:
            print ('Failed to detected LabOne DAQ Server and an associated Zurich Instruments device.'
                ' Check that everything is plugged into the computer.')

    @setting(101, 'List Devices', returns=['*(ws)'])
    def list_devices(self, c):
        """Returns the list of devices. If none have been detected (either because detect_devices has not yet
        been run, or because of a bad connection), this will return an empty array. This is the format required for a DeviceServer
        which this server has not yet transitioned to."""
        names = self.device_list
        length = len(self.device_list)
        IDs = list(range(0,length))
        return list(zip(IDs, names))

    @setting(102, 'Select Device', key=[': Select first device', 's: Select device by name', 'w: Select device by ID'], returns=['s: Name of the selected device'])
    def select_device(self, c, key = None):
        """Select a device for the current context. DOES NOT WORK. Instead, sets the active device ID to the provided dev_ID. If no dev_ID is provided, sets the active
        device to the first device from the device list. Sets the API level to 1, which should provide all the functionality for the HF2LI. Right now, this is a
        server setting, NOT a context setting, so you cannot have multiple connections with different contexts connected to different devices."""
        if key is None:
            self.dev_ID = self.device_list[0]
            self.initPIDAdvisor()
            self.initSweeper()
        elif isinstance(key, str):
            if key in self.device_list:
                self.dev_ID = key
                self.initPIDAdvisor()
                self.initSweeper()
            else:
                print("Provided device key is not in the list of possible devices.")
        else:
            try:
                self.dev_ID = self.device_list[key]
                self.initPIDAdvisor()
                self.initSweeper()
            except:
                print("Provided device key is not in the list of possible devices.")

        return self.dev_ID

    @setting(103,settings = '**s', returns = '')
    def set_settings(self, c, settings):
        """Simultaneously set all the settings described in the settings input. Settings should be a
            list of string and input tuples, where the string provides the node information and the
            input is the required input. For example:
            setting =   [['/%s/demods/*/enable' % self.dev_ID, '0'],
                        ['/%s/demods/*/trigger' % self.dev_ID, '0'],
                        ['/%s/sigouts/*/enables/*' % self.dev_ID, '0'],
                        ['/%s/scopes/*/enable' % self.dev_ID, '0']]
            This function allows changing multiple settings quickly, however it requires knowledge
            of the node names. Most settings that can be set through this function can also be
            set through other functions."""

        for el in settings:
            el[1] = float(el[1])

        yield self.daq.set(settings)

    @setting(104,returns = '')
    def sync(self,c):
        """Perform a global synchronisation between the device and the data server:
            Ensure that the settings have taken effect on the device before setting
            the next configuration."""
        yield self.daq.sync()

    @setting(155, returns = 's')
    def version(self,c):
        """Returns the version of the software installed on this computer"""
        ver = yield self.daq.version()
        returnValue(ver)

#------------------------------------------------------------------------------------------------------------------------------------------#
    """
    The following section of code has all of the commands relevant to basic controls of the lock in reading and output.
    """

    @setting(105,returns = '')
    def disable_outputs(self,c):
        """Create a base instrument configuration: disable all outputs, demods and scopes."""
        general_setting = [['/%s/demods/*/enable' % self.dev_ID, 0],
                           ['/%s/demods/*/trigger' % self.dev_ID, 0],
                           ['/%s/sigouts/*/enables/*' % self.dev_ID, 0],
                           ['/%s/scopes/*/enable' % self.dev_ID, 0]]
        yield self.daq.set(general_setting)
        # Perform a global synchronisation between the device and the data server:
        # Ensure that the settings have taken effect on the device before setting
        # the next configuration.


    @setting(106,input_channel = 'i', on = 'b', returns = '')
    def set_ac(self, c, input_channel, on):
        """Set the AC coupling of the provided input channel (1 indexed) to on, if on is True,
        and to off, if on is False"""
        setting = ['/%s/sigins/%d/ac' % (self.dev_ID, input_channel-1), on],
        yield self.daq.set(setting)

    @setting(107,input_channel = 'i', on = 'b', returns = '')
    def set_imp50(self, c, input_channel, on):
        """Set the input impedance of the provided input channel (1 indexed) to 50 ohms, if on is True,
        and to 1 mega ohm, if on is False"""
        setting = ['/%s/sigins/%d/imp50' % (self.dev_ID, input_channel-1), on],
        yield self.daq.set(setting)

    @setting(108,input_channel = 'i', amplitude = 'v[]', returns = '')
    def set_range(self, c, input_channel, amplitude):
        """Set the input voltage range of the provided input channel (1 indexed) to the provided amplitude in Volts."""
        setting = ['/%s/sigins/%d/range' % (self.dev_ID, input_channel-1), amplitude],
        yield self.daq.set(setting)

    @setting(1080,input_channel = 'i', returns = 'v[]')
    def get_range(self, c, input_channel):
        """Set the input voltage range of the provided input channel (1 indexed) to the provided amplitude in Volts."""
        setting = '/%s/sigins/%d/range' % (self.dev_ID, input_channel-1)
        range = yield self.daq.get(setting, True)
        returnValue(float(range[setting]))

    @setting(109,input_channel = 'i', on = 'b', returns = '')
    def set_diff(self, c, input_channel, on):
        """Set the input mode of the provided input channel (1 indexed) to differential, if on is True,
        and to single ended, if on is False"""
        setting = ['/%s/sigins/%d/diff' % (self.dev_ID, input_channel-1), on],
        yield self.daq.set(setting)

    @setting(110,osc_index= 'i', freq = 'v[]', returns = '')
    def set_oscillator_freq(self,c, osc_index, freq):
        """Set the frequency of the designated oscillator (1 indexed) to the provided frequency. The HF2LI Lock-in has
        two oscillators. """
        setting = ['/%s/oscs/%d/freq' % (self.dev_ID, osc_index-1), freq],
        yield self.daq.set(setting)

    @setting(1110,demod_index= 'i', on = 'b', returns = '')
    def set_demod(self,c, demod_index, on):
        """Turns the specified demodulator on, if on is True, and off, if on is False"""
        setting = ['/%s/demods/%d/enable' % (self.dev_ID, demod_index-1), on],
        yield self.daq.set(setting)

    @setting(111,demod_index= 'i', oscselect = 'i', returns = '')
    def set_demod_osc(self,c, demod_index, oscselect):
        """Sets the provided demodulator to select the provided oscillator as its reference frequency. The HF2LI Lock-in has
        six demodulators and two oscillators."""
        setting = ['/%s/demods/%d/oscselect' % (self.dev_ID, demod_index-1), oscselect-1],
        yield self.daq.set(setting)

    @setting(112,demod_index= 'i', harm = 'i', returns = '')
    def set_demod_harm(self,c, demod_index, harm):
        """Sets the provided demodulator harmonic. Demodulation frequency will be the reference oscillator times the provided
        integer harmonic."""
        setting = ['/%s/demods/%d/harmonic' % (self.dev_ID, demod_index-1), harm],
        yield self.daq.set(setting)

    @setting(113,demod_index= 'i', phase = 'v[]', returns = '')
    def set_demod_phase(self,c, demod_index, phase):
        """Sets the provided demodulator phase."""
        setting = ['/%s/demods/%d/phaseshift' % (self.dev_ID, demod_index-1), phaseshift],
        yield self.daq.set(setting)

    @setting(114,demod_index= 'i', input_channel = 'i', returns = '')
    def set_demod_input(self,c, demod_index, input_channel):
        """Sets the provided demodulator phase."""
        setting = ['/%s/demods/%d/adcselect' % (self.dev_ID, demod_index-1), input_channel-1],
        yield self.daq.set(setting)

    @setting(115,demod_index= 'i', time_constant = 'v[]', returns = '')
    def set_demod_time_constant(self,c, demod_index, time_constant):
        """Sets the provided demodulator time constant in seconds."""
        setting = ['/%s/demods/%d/timeconstant' % (self.dev_ID, demod_index-1), time_constant],
        yield self.daq.set(setting)

    @setting(1150,demod_index= 'i', returns = 'v[]')
    def get_demod_time_constant(self,c, demod_index):
        """Sets the provided demodulator time constant in seconds."""
        setting = '/%s/demods/%d/timeconstant' % (self.dev_ID, demod_index-1)
        tc = yield self.daq.get(setting, True)
        returnValue(float(tc[setting]))

    @setting(117,output_channel = 'i', on = 'b', returns = '')
    def set_output(self, c, output_channel, on):
        """Turns the output of the provided output channel (1 indexed) to on, if on is True,
        and to off, if on is False"""
        setting = ['/%s/sigouts/%d/on' % (self.dev_ID, output_channel-1), on],
        yield self.daq.set(setting)

    @setting(118,output_channel = 'i', amp = 'v[]', returns = '')
    def set_output_amplitude(self, c, output_channel, amp):
        """Sets the output amplitude of the provided output channel (1 indexed) to the provided input amplitude
        in units of the output range."""
        if output_channel == 1:
            setting = ['/%s/sigouts/%d/amplitudes/6' % (self.dev_ID, output_channel-1), amp],
        elif output_channel == 2:
            setting = ['/%s/sigouts/%d/amplitudes/7' % (self.dev_ID, output_channel-1), amp],
        yield self.daq.set(setting)

    @setting(1180,output_channel = 'i', returns = 'v[]')
    def get_output_amplitude(self, c, output_channel):
        """Gets the output amplitude of the provided output channel (1 indexed) in units of the output range."""
        if output_channel == 1:
            setting = '/%s/sigouts/%d/amplitudes/6' % (self.dev_ID, output_channel-1)
        elif output_channel == 2:
            setting = '/%s/sigouts/%d/amplitudes/7' % (self.dev_ID, output_channel-1)
        dic = yield self.daq.get(setting, True)
        amp = float(dic[setting])
        returnValue(amp)

    @setting(119,output_channel = 'i', range = 'v[]', returns = '')
    def set_output_range(self, c, output_channel, range):
        """Sets the output range of the provided output channel (1 indexed) to the provided input amplitude
        in units of volts. Will automatically go to the value just above the desired provided range. Sets to
        10 mV, 100 mV, 1 V or 10V."""
        setting = ['/%s/sigouts/%d/range' % (self.dev_ID, output_channel-1), range],
        yield self.daq.set(setting)

    @setting(120,output_channel = 'i', returns = 'v[]')
    def get_output_range(self, c, output_channel):
        """Gets the output amplitude of the provided output channel (1 indexed) to the provided input amplitude
        in units of the output range."""
        setting = '/%s/sigouts/%d/range' % (self.dev_ID, output_channel-1)
        dic = yield self.daq.get(setting,True)
        range = float(dic[setting])
        returnValue(range)

#------------------------------------------------------------------------------------------------------------------------------------------#
    """
    The following section of code has all of the commands relevant to using the HF2LI built in sweeper.
    """

    @setting(121,start = 'v[]', stop = 'v[]', samplecount  = 'i', sweep_param = 's', demod = 'i', log = 'b', bandwidthcontrol = 'i', bandwidth = 'v[]', bandwidthoverlap = 'b', loopcount = 'i', settle_time = 'v[]', settle_inaccuracy = 'v[]', averaging_tc = 'v[]', averaging_sample = 'v[]', returns = 'b')
    def create_sweep_object(self,c,start,stop, samplecount, sweep_param, demod = 1, log = False, bandwidthcontrol = 2, bandwidth = 1000, bandwidthoverlap = False, loopcount = 1, settle_time = 0, settle_inaccuracy = 0.001, averaging_tc = 5, averaging_sample = 5):
        """Sweeps the provided sweep parameter from the provided start value to the provided stop value with
        the desired number of points. The sweep records all data at each point in the sweep. The sweeper will
        not turn on any outputs or configure anything else. It only sweeps the parameter and records data.
        Available sweep_param inputs are (spaces included): \r\n
        oscillator 1 \r\n
        oscillator 2 \r\n
        output 1 amplitude \r\n
        output 2 amplitude \r\n
        output 1 offset \r\n
        output 2 offset \r\n
        Returns the 4 by samplecount array with the first column corresponding to grid of the swept parameter,
        the second corresponds to the demodulator R, the third to the phase, and the fourth to the frequency.
        Loop count greater than 1 not yet implemented. """

        self.sweeper_path = '/%s/demods/%d/sample' % (self.dev_ID, demod - 1)
        #Set the parameter to be swept
        sweep_param_set = False
        if sweep_param == "oscillator 1":
            yield self.sweeper.set('sweep/gridnode', 'oscs/0/freq')
            sweep_param_set = True
        elif sweep_param == "oscillator 2":
            yield self.sweeper.set('sweep/gridnode', 'oscs/1/freq')
            sweep_param_set = True
        elif sweep_param == "output 1 amplitude":
            yield self.sweeper.set('sweep/gridnode', 'sigouts/0/amplitudes/6')
            sweep_param_set = True
        elif sweep_param == "output 2 amplitude":
            yield self.sweeper.set('sweep/gridnode', 'sigouts/1/amplitudes/7')
            sweep_param_set = True
        elif sweep_param == "output 1 offset":
            yield self.sweeper.set('sweep/gridnode', 'sigouts/0/offset')
            sweep_param_set = True
        elif sweep_param == "output 2 offset":
            yield self.sweeper.set('sweep/gridnode', 'sigouts/1/offset')
            sweep_param_set = True

        if sweep_param_set == True:
            #Set the start and stop points
            if start <= stop:
                yield self.sweeper.set('sweep/start', start)
                yield self.sweeper.set('sweep/stop', stop)
                yield self.sweeper.set('sweep/scan', 0)
            else:
                yield self.sweeper.set('sweep/start', stop)
                yield self.sweeper.set('sweep/stop', start)
                yield self.sweeper.set('sweep/scan', 3)

            yield self.sweeper.set('sweep/samplecount', samplecount)

            #Specify linear or logarithmic grid spacing. Off by default
            yield self.sweeper.set('sweep/xmapping', log)
            # Automatically control the demodulator bandwidth/time constants used.
            # 0=manual, 1=fixed, 2=auto
            # Note: to use manual and fixed, sweep/bandwidth has to be set to a value > 0.
            yield self.sweeper.set('sweep/bandwidthcontrol', bandwidthcontrol)
            if bandwidthcontrol == 0 or bandwidthcontrol == 1:
                yield self.sweeper.set('sweep/bandwidth',bandwidth)
            # Sets the bandwidth overlap mode (default 0). If enabled, the bandwidth of
            # a sweep point may overlap with the frequency of neighboring sweep
            # points. The effective bandwidth is only limited by the maximal bandwidth
            # setting and omega suppression. As a result, the bandwidth is independent
            # of the number of sweep points. For frequency response analysis bandwidth
            # overlap should be enabled to achieve maximal sweep speed (default: 0). 0 =
            # Disable, 1 = Enable.
            yield self.sweeper.set('sweep/bandwidthoverlap', bandwidthoverlap)

            # Specify the number of sweeps to perform back-to-back.
            yield self.sweeper.set('sweep/loopcount', loopcount)

            #Specify the settling time between data points.
            yield self.sweeper.set('sweep/settling/time', settle_time)

            # The sweep/settling/inaccuracy' parameter defines the settling time the
            # sweeper should wait before changing a sweep parameter and recording the next
            # sweep data point. The settling time is calculated from the specified
            # proportion of a step response function that should remain. The value
            # provided here, 0.001, is appropriate for fast and reasonably accurate
            # amplitude measurements. For precise noise measurements it should be set to
            # ~100n.
            # Note: The actual time the sweeper waits before recording data is the maximum
            # time specified by sweep/settling/time and defined by
            # sweep/settling/inaccuracy.
            yield self.sweeper.set('sweep/settling/inaccuracy', settle_inaccuracy)

            # Set the minimum time to record and average data. By default set to 10 demodulator
            # filter time constants.
            yield self.sweeper.set('sweep/averaging/tc', averaging_tc)

            # Minimal number of samples that we want to record and average. Note,
            # the number of samples used for averaging will be the maximum number of
            # samples specified by either sweep/averaging/tc or sweep/averaging/sample.
            # By default this is set to 5.
            yield self.sweeper.set('sweep/averaging/sample', averaging_sample)


            #Subscribe to path defined previously
            yield self.sweeper.subscribe(self.sweeper_path)

            returnValue(True)
        else:
            print('Desired sweep parameter does not exist')
            returnValue(False)

    @setting(122, returns = 'b')
    def start_sweep(self,c):
        success = False
        if self.sweeper is not None:
            yield self.sweeper.execute()
            success = True
        returnValue(success)

    @setting(123, returns = '**v[]')
    def read_latest_values(self,c):
        return_flat_dict = True
        data = yield self.sweeper.read(return_flat_dict)
        demod_data = data[self.sweeper_path]

        grid = demod_data[0][0]['grid']
        R = np.abs(demod_data[0][0]['x'] + 1j*demod_data[0][0]['y'])
        #phi = np.angle(demod_data[0][0]['x'] + 1j*demod_data[0][0]['y'], True)
        phi = 180*np.arctan2(demod_data[0][0]['y'], demod_data[0][0]['x'])/np.pi
        frequency  = demod_data[0][0]['frequency']

        formatted_data = [[],[],[],[]]
        length = len(grid)
        for i in range(0,length):
            try:
                formatted_data[0].append(float(grid[i]))
                formatted_data[1].append(float(frequency[i]))
                formatted_data[2].append(float(R[i]))
                formatted_data[3].append(float(phi[i]))
            except:
                pass

        returnValue(formatted_data)

    @setting(124,returns = 'b')
    def sweep_complete(self,c):
        '''Checks to see if there's a sweep was completed. Returns True if the sweeper is not
        currently sweeping. Returns False if the sweeper is mid sweep.'''
        if self.sweeper is not None:
            done = yield self.sweeper.finished()
        else:
            done = True
        returnValue(done)

    @setting(125,returns = 'v[]')
    def sweep_time_remaining(self,c):
        if self.sweeper is not None:
            time = yield self.sweeper.get('sweep/remainingtime')
            time = time['remainingtime'][0]
        else:
            time = float('nan')
        returnValue(time)

    @setting(126, returns = 'b')
    def stop_sweep(self,c):
        success = False
        if self.sweeper is not None:
            yield self.sweeper.finish()
            success = True
        returnValue(success)

    @setting(127,returns = '')
    def clear_sweep(self,c):
        try:
            # Stop the sweeper thread and clear the memory.
            self.sweeper.unsubscribe(path)
            self.sweeper.clear()
        except:
            pass

#------------------------------------------------------------------------------------------------------------------------------------------#
    """
    The following section of code has all of the commands relevant to modifing the PLL module options.
    """

    @setting(129,PLL = 'i', freq = 'v[]', returns = '')
    def set_PLL_freqcenter(self, c, PLL, freq):
        """Sets the center frequency of the specified PLL (either 1 or 2)"""
        setting = ['/%s/plls/%d/freqcenter' % (self.dev_ID, PLL-1), freq],
        yield self.daq.set(setting)

    @setting(130, PLL = 'i', returns = 'v[]')
    def get_PLL_freqcenter(self, c, PLL):
        """Gets the PLL center frequency of the specified PLL (either 1 or 2)."""
        setting = '/%s/plls/%d/freqcenter' % (self.dev_ID, PLL-1)
        dic = yield self.daq.get(setting,True)
        freq = float(dic[setting])
        returnValue(freq)

    @setting(131,PLL = 'i', freq = 'v[]', returns = '')
    def set_PLL_freqrange(self, c, PLL, freq):
        """Sets the frequency range of the specified PLL (either 1 or 2)"""
        setting = ['/%s/plls/%d/freqrange' % (self.dev_ID, PLL-1), freq],
        yield self.daq.set(setting)

    @setting(132, PLL = 'i', returns = 'v[]')
    def get_PLL_freqrange(self, c, PLL):
        """Gets the PLL frequency range of the specified PLL (either 1 or 2)."""
        setting = '/%s/plls/%d/freqrange' % (self.dev_ID, PLL-1)
        dic = yield self.daq.get(setting,True)
        freq = float(dic[setting])
        returnValue(freq)

    @setting(133,PLL = 'i', harm = 'i', returns = '')
    def set_PLL_harmonic(self, c, PLL, harm):
        """Sets the phase detector harmonic (1 or 2) of the specified PLL (either 1 or 2)"""
        setting = ['/%s/plls/%d/harmonic' % (self.dev_ID, PLL-1), harm],
        yield self.daq.set(setting)

    @setting(134, PLL = 'i', returns = 'i')
    def get_PLL_harmonic(self, c, PLL):
        """Gets the phase detector harmonic of the specified PLL (either 1 or 2)."""
        setting = '/%s/plls/%d/harmonic' % (self.dev_ID, PLL-1)
        dic = yield self.daq.get(setting,True)
        harm = int(dic[setting])
        returnValue(harm)

    @setting(135,PLL = 'i', tc = 'v[]', returns = '')
    def set_PLL_TC(self, c, PLL, tc):
        """Sets the time constant of the specified PLL (either 1 or 2)"""
        setting = ['/%s/plls/%d/timeconstant' % (self.dev_ID, PLL-1), tc],
        yield self.daq.set(setting)

    @setting(136, PLL = 'i', returns = 'v[]')
    def get_PLL_TC(self, c, PLL):
        """Gets the PLL center frequency of the specified PLL (either 1 or 2)."""
        setting = '/%s/plls/%d/timeconstant' % (self.dev_ID, PLL-1)
        dic = yield self.daq.get(setting,True)
        tc = float(dic[setting])
        returnValue(tc)

    @setting(137,PLL = 'i', order = 'i', returns = '')
    def set_PLL_filterorder(self, c, PLL, order):
        """Sets the filter order (1 through 8) of the specified PLL (either 1 or 2)"""
        setting = ['/%s/plls/%d/order' % (self.dev_ID, PLL-1), order],
        yield self.daq.set(setting)

    @setting(138, PLL = 'i', returns = 'i')
    def get_PLL_filterorder(self, c, PLL):
        """Gets the filter order of the specified PLL (either 1 or 2)."""
        setting = '/%s/plls/%d/order' % (self.dev_ID, PLL-1)
        dic = yield self.daq.get(setting,True)
        order = int(dic[setting])
        returnValue(order)

    @setting(139,PLL = 'i', setpoint = 'v[]', returns = '')
    def set_PLL_setpoint(self, c, PLL, setpoint):
        """Sets the phase setpoint in degrees of the specified PLL (either 1 or 2)"""
        setting = ['/%s/plls/%d/setpoint' % (self.dev_ID, PLL-1), setpoint],
        yield self.daq.set(setting)

    @setting(140, PLL = 'i', returns = 'v[]')
    def get_PLL_setpoint(self, c, PLL):
        """Gets the phase setpoint of the specified PLL (either 1 or 2)."""
        setting = '/%s/plls/%d/setpoint' % (self.dev_ID, PLL-1)
        dic = yield self.daq.get(setting,True)
        setpoint = float(dic[setting])
        returnValue(setpoint)

    @setting(141,PLL = 'i', P = 'v[]', returns = '')
    def set_PLL_P(self, c, PLL, P):
        """Sets the proportional term of the specified PLL (either 1 or 2) PID loop"""
        setting = ['/%s/plls/%d/p' % (self.dev_ID, PLL-1), P],
        yield self.daq.set(setting)

    @setting(142, PLL = 'i', returns = 'v[]')
    def get_PLL_P(self, c, PLL):
        """Gets the proportional term of the specified PLL (either 1 or 2) PID loop"""
        setting = '/%s/plls/%d/p' % (self.dev_ID, PLL-1)
        dic = yield self.daq.get(setting,True)
        P = float(dic[setting])
        returnValue(P)

    @setting(143,PLL = 'i', I = 'v[]', returns = '')
    def set_PLL_I(self, c, PLL, I):
        """Sets the intergral term of the specified PLL (either 1 or 2) PID loop"""
        setting = ['/%s/plls/%d/i' % (self.dev_ID, PLL-1), I],
        yield self.daq.set(setting)

    @setting(144, PLL = 'i', returns = 'v[]')
    def get_PLL_I(self, c, PLL):
        """Gets the integral term of the specified PLL (either 1 or 2) PID loop"""
        setting = '/%s/plls/%d/i' % (self.dev_ID, PLL-1)
        dic = yield self.daq.get(setting,True)
        I = float(dic[setting])
        returnValue(I)

    @setting(145,PLL = 'i', D = 'v[]', returns = '')
    def set_PLL_D(self, c, PLL, D):
        """Sets the derivative term of the specified PLL (either 1 or 2) PID loop"""
        setting = ['/%s/plls/%d/d' % (self.dev_ID, PLL-1), D],
        yield self.daq.set(setting)

    @setting(146, PLL = 'i', returns = 'v[]')
    def get_PLL_D(self, c, PLL):
        """Gets the derivative term of the specified PLL (either 1 or 2) PID loop"""
        setting = '/%s/plls/%d/d' % (self.dev_ID, PLL-1)
        dic = yield self.daq.get(setting,True)
        D = float(dic[setting])
        returnValue(D)

    @setting(147,PLL = 'i', returns = '')
    def set_PLL_on(self, c, PLL):
        """Enables the PLL"""
        setting = ['/%s/plls/%d/enable' % (self.dev_ID, PLL-1), 1],
        yield self.daq.set(setting)

    @setting(148,PLL = 'i', returns = '')
    def set_PLL_off(self, c, PLL):
        """Turns off the PLL"""
        setting = ['/%s/plls/%d/enable' % (self.dev_ID, PLL-1), 0],
        yield self.daq.set(setting)

    @setting(1480,PLL = 'i', returns = 'b')
    def get_PLL_on(self, c, PLL):
        """Turns off the PLL"""
        setting = '/%s/plls/%d/enable' % (self.dev_ID, PLL-1)
        dic = yield self.daq.get(setting, True)
        on = bool(dic[setting])
        returnValue(on)

    @setting(149,PLL = 'i', sigin = 'i', returns = '')
    def set_PLL_input(self, c, PLL, sigin):
        """Sets the PLL input signal (1/2 correspond to sig in 1/2, 3/4 correspond to Aux In 1/2, and 5/6 correspond to
            DIO D0/D1"""
        setting = ['/%s/plls/%d/adcselect' % (self.dev_ID, PLL-1), sigin-1],
        yield self.daq.set(setting)

    @setting(150, PLL = 'i', returns = 'v[]')
    def get_PLL_input(self, c, PLL):
        """Gets the PID input signal channel"""
        setting = '/%s/plls/%d/adcselect' % (self.dev_ID, PLL-1)
        dic = yield self.daq.get(setting,True)
        sigin = int(dic[setting])
        returnValue(sigin+1)

    '''
    Following two methods currently do not work, also don't really ever need to be used. Kept commented out in case someone
    needs them in the future and wants a starting point. Farily certain that PLL rate cannot be set, through reading it
    should be possible.
    @setting(151,PLL = 'i', rate = 'v[]', returns = '')
    def set_PLL_rate(self, c, PLL, rate):
        """Sets the PLL PID sampling rate"""
        setting = ['/%s/plls/%d/rate' % (self.dev_ID, PLL-1), rate],
        yield self.daq.set(setting)

    @setting(152, PLL = 'i', returns = 'v[]')
    def get_PLL_rate(self, c, PLL):
        """Gets the PLL PID sampling rate"""
        setting = '/%s/plls/%d/rate' % (self.dev_ID, PLL-1)
        dic = yield self.daq.get(setting,True)
        rate = float(dic[setting])
        returnValue(rate)
    '''

    @setting(174,PLL_index = 'i', on = 'b', returns = '')
    def set_PLL_autocenter(self, c, PLL_index, on):
        """Set the PLL auto center frequency of the provided PLL (1 indexed) to on, if on is True,
        and to off, if on is False"""
        setting = ['/%s/plls/%d/autocenter' % (self.dev_ID, PLL_index-1), on],
        yield self.daq.set(setting)

    @setting(175,PLL_index = 'i', on = 'b', returns = '')
    def set_PLL_autotc(self, c, PLL_index, on):
        """Set the PLL auto time constant of the provided PLL (1 indexed) to on, if on is True,
        and to off, if on is False"""
        setting = ['/%s/plls/%d/autotimeconstant' % (self.dev_ID, PLL_index-1), on],
        yield self.daq.set(setting)

    @setting(176,PLL_index = 'i', on = 'b', returns = '')
    def set_PLL_autopid(self, c, PLL_index, on):
        """Set the PLL auto pid of the provided PLL (1 indexed) to on, if on is True,
        and to off, if on is False"""
        setting = ['/%s/plls/%d/autopid' % (self.dev_ID, PLL_index-1), on],
        yield self.daq.set(setting)

    @setting(1520, PLL = 'i', returns = 'i')
    def get_PLL_lock(self, c, PLL):
        """Returns 0 if the PLL is NOT locked, and returns 1 if the PLL is locked."""
        setting = '/%s/plls/%d/locked' % (self.dev_ID, PLL-1)
        lock = yield self.daq.getInt(setting)
        returnValue(lock)

    @setting(1521,PLL_index = 'i', returns = 'v[]')
    def get_pll_freqdelta(self, c, PLL_index):
        """Gets the PLL (1 or 2) latest output freq delta."""
        setting = '/%s/plls/%d/freqdelta' % (self.dev_ID, PLL_index-1)
        val = yield self.daq.getDouble(setting)
        returnValue(val)

    @setting(1522,PLL_index = 'i', returns = 'v[]')
    def get_pll_error(self, c, PLL_index):
        """Gets the Auxilary Output (1 through 4) latest output error."""
        setting = '/%s/plls/%d/error' % (self.dev_ID, PLL_index-1)
        val = yield self.daq.getDouble(setting)
        returnValue(val)

#------------------------------------------------------------------------------------------------------------------------------------------#
    """
    The following section of code has all of the commands relevant to using the PID advisor
    """

    @setting(128, PLL_index = 'i', targetBW = 'v[]', pidMode = 'i', returns = 'b')
    def advise_PLL_PID(self, c, PLL_index, targetBW, pidMode):
        """Simulates and computes values for the PLL PID loop. Make sure that the Harmonic
        and Filter Order is set on the advisor before running. Requires the index of the PLL,
        the desired BW of the PLL PID, and the PID Mode (0 is P, 1 is I, 2 is PI, and 3 is PID)
        Function returns true once calculations are complete. Computer parameters should be
        retrieved using the appropriate get commands."""

        yield self.pidAdvisor.set('pidAdvisor/pid/type', 'pll')

        if pidMode == 0:
            #P mode
            yield self.pidAdvisor.set('pidAdvisor/pid/mode',1)
        elif pidMode == 1:
            #I mode
            yield self.pidAdvisor.set('pidAdvisor/pid/mode',2)
        elif pidMode == 2:
            #PI mode
            yield self.pidAdvisor.set('pidAdvisor/pid/mode',3)
        elif pidMode == 3:
            #PID mode
            yield self.pidAdvisor.set('pidAdvisor/pid/mode',7)

        yield self.pidAdvisor.set('pidAdvisor/pid/targetbw', targetBW)

        # PID index to use (first PID of device: 0)
        yield self.pidAdvisor.set('pidAdvisor/index', PLL_index-1)

        #Reset everything to 0 prior to calculation
        yield self.pidAdvisor.set('pidAdvisor/pid/p', 0)
        yield self.pidAdvisor.set('pidAdvisor/pid/i', 0)
        yield self.pidAdvisor.set('pidAdvisor/pid/d', 0)
        yield self.pidAdvisor.set('pidAdvisor/calculate', 0)

        # Start the module thread
        yield self.pidAdvisor.execute()
        yield self.sleep(2.0)
        # Advise
        yield self.pidAdvisor.set('pidAdvisor/calculate', 1)
        print('Starting advising. Optimization process may run up to a minute...')
        reply = yield self.pidAdvisor.get('pidAdvisor/calculate')

        t_start = time.time()
        t_timeout = t_start + 60
        while reply['calculate'][0] == 1:
            reply = yield self.pidAdvisor.get('pidAdvisor/calculate')
            if time.time() > t_timeout:
                yield self.pidAdvisor.finish()
                raise Exception("PID advising failed due to timeout.")

        print(("Advice took {:0.1f} s.".format(time.time() - t_start)))

        """
        # Get all calculated parameters.
        result = yield self.pidAdvisor.get('pidAdvisor/*')
        # Check that the dictionary returned by poll contains the data that are needed.
        assert result, "pidAdvisor returned an empty data dictionary?"
        assert 'pid' in result, "data dictionary has no key 'pid'"
        assert 'step' in result, "data dictionary has no key 'step'"
        assert 'bode' in result, "data dictionary has no key 'bode'"
        """

        returnValue(True)

    @setting(156, P = 'v[]', returns = '')
    def set_Advisor_P(self, c, P):
        """Sets the proportional term on the PID Advisor"""
        setting = ['pidAdvisor/pid/p', P],
        yield self.pidAdvisor.set(setting)

    @setting(157, returns = 'v[]')
    def get_Advisor_P(self, c):
        """Gets the proportional term on the PID Advisor"""
        setting = 'pidAdvisor/pid/p'
        dic = yield self.pidAdvisor.get(setting,True)
        P = float(dic['/pid/p'])
        returnValue(P)

    @setting(158,I = 'v[]', returns = '')
    def set_Advisor_I(self, c, I):
        """Sets the integral term on the PID Advisor"""
        setting = ['pidAdvisor/pid/i', I],
        yield self.pidAdvisor.set(setting)

    @setting(159, returns = 'v[]')
    def get_Advisor_I(self, c):
        """Gets the integral term on the PID Advisor"""
        setting = 'pidAdvisor/pid/i'
        dic = yield self.pidAdvisor.get(setting,True)
        I = float(dic['/pid/i'])
        returnValue(I)

    @setting(160,D = 'v[]', returns = '')
    def set_Advisor_D(self, c, D):
        """Sets the derivative term on the PID Advisor"""
        setting = ['pidAdvisor/pid/d', D],
        yield self.pidAdvisor.set(setting)

    @setting(161, returns = 'v[]')
    def get_Advisor_D(self, c):
        """Gets the derivative term on the PID Advisor"""
        setting = 'pidAdvisor/pid/d'
        dic = yield self.pidAdvisor.get(setting,True)
        D = float(dic['/pid/d'])
        returnValue(D)

    @setting(162, returns = 'v[]')
    def get_Advisor_PM(self, c):
        """Gets the PLL PID phase margin"""
        setting = 'pidAdvisor/pm'
        dic = yield self.pidAdvisor.get(setting,True)
        PM = float(dic['/pm'])
        returnValue(PM)

    @setting(163, returns = 'i')
    def get_Advisor_stable(self, c):
        """Returns whether or not the current parameters in the PID Advisor are stable."""
        setting = 'pidAdvisor/stable'
        dic = yield self.pidAdvisor.get(setting,True)
        stable = int(dic['/stable'])
        returnValue(stable)

    @setting(164, tc = 'v[]', returns = '')
    def set_Advisor_tc(self, c, tc):
        """Sets the PLL PID adivsor tc"""
        setting = ['pidAdvisor/demod/timeconstant', tc],
        yield self.pidAdvisor.set(setting)

    @setting(165, returns = 'v[]')
    def get_Advisor_tc(self, c):
        """Gets the PLL PID adivsor tc"""
        setting = 'pidAdvisor/demod/timeconstant'
        dic = yield self.pidAdvisor.get(setting,True)
        tc = float(dic['/demod/timeconstant'])
        returnValue(tc)

    @setting(166,rate = 'v[]', returns = '')
    def set_Advisor_rate(self, c, rate):
        """Sets the PLL PID advisor sampling rate"""
        setting = ['pidAdvisor/pid/rate', rate],
        yield self.pidAdvisor.set(setting)

    @setting(167, returns = 'v[]')
    def get_Advisor_rate(self, c):
        """Gets the PLL PID advisor sampling rate"""
        setting = 'pidAdvisor/pid/rate'
        dic = yield self.pidAdvisor.get(setting,True)
        rate = float(dic['/pid/rate'])
        returnValue(rate)

    @setting(168, harm  = 'i', returns = '')
    def set_Advisor_harmonic(self, c, harm):
        """Sets the PLL PID advisor harmonic (can be 1 or 2)"""
        setting = ['pidAdvisor/demod/harmonic', harm],
        yield self.pidAdvisor.set(setting)

    @setting(169, returns = 'i')
    def get_Advisor_harmonic(self, c):
        """Gets the PLL PID advisor sampling rate"""
        setting = 'pidAdvisor/demod/harmonic'
        dic = yield self.pidAdvisor.get(setting,True)
        rate = int(dic['/demod/harmonic'])
        returnValue(rate)

    @setting(170, order = 'i', returns = '')
    def set_Advisor_filterorder(self, c, order):
        """Sets the PLL PID advisor harmonic (can be 1 or 2)"""
        setting = ['pidAdvisor/demod/order', order],
        yield self.pidAdvisor.set(setting)

    @setting(171, returns = 'i')
    def get_Advisor_filterorder(self, c):
        """Gets the PLL PID advisor sampling rate"""
        setting = 'pidAdvisor/demod/order'
        dic = yield self.pidAdvisor.get(setting,True)
        order = int(dic['/demod/order'])
        returnValue(order)

    @setting(172, returns = 'v[]')
    def get_Advisor_simbw(self, c):
        """Gets the PLL PID advisor simulated bandwidth"""
        setting = 'pidAdvisor/bw'
        dic = yield self.pidAdvisor.get(setting,True)
        bw = float(dic['/bw'])
        returnValue(bw)

    @setting(173, returns = 'b')
    def get_advisor_calc(self,c):
        """Returns True if the pid advisor is mid calculation. Fasle otherwise."""
        reply = yield self.pidAdvisor.get('pidAdvisor/calculate')
        if reply['calculate'][0] == 1:
            returnValue(True)
        else:
            returnValue(False)

#------------------------------------------------------------------------------------------------------------------------------------------#
    """
    The following section of code has all of the commands relevant to modifing the auxiliary outputs.
    """

    @setting(177, aux_out_index = 'i', signal_index = 'i', returns = '')
    def set_aux_output_signal(self, c, aux_out_index, signal_index):
        """Set the Auxilary Output Signal (1 through 4) to be proportional to the specified signal.
        Signal index: Corresponding Signal
         0          : Demod X
         1          : Demod Y
         2          : Demod R
         3          : Demod Theta
         4          : PLL 1 df
         5          : PLL 2 df
        -2          : PID 1 Out
        -3          : PID 2 Out
        -4          : PID 3 Out
        -5          : PID 4 Out
        -1          : Manual"""

        setting = ['/%s/auxouts/%d/outputselect' % (self.dev_ID, aux_out_index-1), signal_index],
        yield self.daq.set(setting)

    @setting(178, aux_out_index = 'i', returns = 'i')
    def get_aux_output_signal(self, c, aux_out_index):
        """Get the Auxilary Output Signal (1 through 4) to be proportional to the specified signal.
        Signal index: Corresponding Signal
         0          : Demod X
         1          : Demod Y
         2          : Demod R
         3          : Demod Theta
         4          : PLL 1 df
         5          : PLL 2 df
        -2          : PID 1 Out
        -3          : PID 2 Out
        -4          : PID 3 Out
        -5          : PID 4 Out
        -1          : Manual"""

        setting = '/%s/auxouts/%d/outputselect' % (self.dev_ID, aux_out_index-1)
        dic = yield self.daq.get(setting,True)
        sig_ind = int(dic[setting])
        returnValue(sig_ind)

    @setting(179, aux_out_index = 'i', demod_index = 'i', returns = '')
    def set_aux_output_demod(self, c, aux_out_index, demod_index):
        """If the Auxilary Output Signal (1 through 4) is set to a deomulator signal (signal index 0 through 3),
        then this allows you to specify which demodulator is being used (1 through 6)."""
        setting = ['/%s/auxouts/%d/demodselect' % (self.dev_ID, aux_out_index-1), demod_index - 1],
        yield self.daq.set(setting)

    @setting(180, aux_out_index = 'i', returns = 'i')
    def get_aux_output_demod(self, c, aux_out_index):
        """If the Auxilary Output Signal (1 through 4) is set to a deomulator signal (signal index 0 through 3),
        then this allows you to get which demodulator is being used (1 through 6)."""
        setting = '/%s/auxouts/%d/demodselect' % (self.dev_ID, aux_out_index-1)
        dic = yield self.daq.get(setting,True)
        demod = int(dic[setting])+1
        returnValue(demod)

    @setting(181, aux_out_index = 'i', scale = 'v[]', returns = '')
    def set_aux_output_scale(self, c, aux_out_index, scale):
        """Sets the Auxilary Output (1 through 4) Scale, or multiplier value."""

        setting = ['/%s/auxouts/%d/scale' % (self.dev_ID, aux_out_index-1), scale],
        yield self.daq.set(setting)

    @setting(182, aux_out_index = 'i', returns = 'v[]')
    def get_aux_output_scale(self, c, aux_out_index):
        """Gets the Auxilary Output (1 through 4) Scale, or multiplier value."""
        setting = '/%s/auxouts/%d/scale' % (self.dev_ID, aux_out_index-1)
        dic = yield self.daq.get(setting,True)
        scale = float(dic[setting])
        returnValue(scale)

    @setting(183, aux_out_index = 'i', offset = 'v[]', returns = '')
    def set_aux_output_offset(self, c, aux_out_index, offset):
        """Sets the Auxilary Output (1 through 4) offset value."""
        setting = ['/%s/auxouts/%d/offset' % (self.dev_ID, aux_out_index-1), offset],
        yield self.daq.set(setting)

    @setting(184, aux_out_index = 'i', returns = 'v[]')
    def get_aux_output_offset(self, c, aux_out_index):
        """Gets the Auxilary Output (1 through 4) offset value."""
        setting = '/%s/auxouts/%d/offset' % (self.dev_ID, aux_out_index-1)
        dic = yield self.daq.get(setting,True)
        offset = float(dic[setting])
        returnValue(offset)

    @setting(1810, aux_out_index = 'i', scale = 'v[]', returns = '')
    def set_aux_output_monitorscale(self, c, aux_out_index, scale):
        """Sets the Auxilary Output (1 through 4) monitor scale, or multiplier value. This is the scale
        that gets applied when the signal of the aux output is monitoring a PID output."""
        setting = ['/%s/pids/%d/monitorscale' % (self.dev_ID, aux_out_index-1), scale],
        yield self.daq.set(setting)

    @setting(1820, aux_out_index = 'i', returns = 'v[]')
    def get_aux_output_monitorscale(self, c, aux_out_index):
        """Gets the Auxilary Output (1 through 4) monitor cale, or multiplier value. This is the scale
        that gets applied when the signal of the aux output is monitoring a PID output."""
        setting = '/%s/pids/%d/monitorscale' % (self.dev_ID, aux_out_index-1)
        dic = yield self.daq.get(setting,True)
        scale = float(dic[setting])
        returnValue(scale)

    @setting(1830, aux_out_index = 'i', offset = 'v[]', returns = '')
    def set_aux_output_monitoroffset(self, c, aux_out_index, offset):
        """Sets the Auxilary Output (1 through 4) offset value. This is the offset
        that gets applied when the signal of the aux output is monitoring a PID output."""
        setting = ['/%s/pids/%d/monitoroffset' % (self.dev_ID, aux_out_index-1), offset],
        yield self.daq.set(setting)

    @setting(1840, aux_out_index = 'i', returns = 'v[]')
    def get_aux_output_monitoroffset(self, c, aux_out_index):
        """Gets the Auxilary Output (1 through 4) offset value. This is the offset
        that gets applied when the signal of the aux output is monitoring a PID output."""
        setting = '/%s/pids/%d/monitoroffset' % (self.dev_ID, aux_out_index-1)
        dic = yield self.daq.get(setting,True)
        offset = float(dic[setting])
        returnValue(offset)

    @setting(185,aux_out_index = 'i', returns = 'v[]')
    def get_aux_output_value(self,c,aux_out_index):
        """Gets the Auxilary Output (1 through 4) latest output value."""
        setting = '/%s/auxouts/%d/value' % (self.dev_ID, aux_out_index-1)
        val = yield self.daq.getDouble(setting)
        returnValue(val)

    @setting(1850,aux_in_index = 'i', returns = 'v[]')
    def get_aux_input_value(self,c,aux_in_index):
        """Gets the Auxilary Input (1 through 2) latest input value."""
        setting = '/%s/auxins/0/values/%d' % (self.dev_ID, aux_in_index-1)
        val = yield self.daq.getDouble(setting)
        returnValue(val)

#------------------------------------------------------------------------------------------------------------------------------------------#
    """
    The following section of code has all of the commands relevant to modifing the PID module options.
    """

    @setting(186, pid_index = 'i', signal_index = 'i', returns = '')
    def set_pid_input_signal(self, c, pid_index, signal_index):
        """Set the PID Input Signal (1 through 4) to be the specified signal.
        Signal index: Corresponding Signal
         0          : Demod X
         1          : Demod Y
         2          : Demod R
         3          : Demod Theta
         4          : Aux Input
         5          : Aux Output
         6          : Modulation
         7          : Dual Frequency Tracking |Z(i+1)| - |Z(i)|
         8          : Demod X(i+1)-X(i)
         9          : Demod|Z(i+1)-Z(i)|
        10          : Oscillator Frequency"""

        setting = ['/%s/pids/%d/input' % (self.dev_ID, pid_index-1), signal_index],
        yield self.daq.set(setting)

    @setting(187, pid_index = 'i', returns = 'i')
    def get_pid_input_signal(self, c, pid_index):
        """Gets the PID Input Signal (1 through 4).
        Signal index: Corresponding Signal
         0          : Demod X
         1          : Demod Y
         2          : Demod R
         3          : Demod Theta
         4          : Aux Input
         5          : Aux Output
         6          : Modulation
         7          : Dual Frequency Tracking |Z(i+1)| - |Z(i)|
         8          : Demod X(i+1)-X(i)
         9          : Demod|Z(i+1)-Z(i)|
        10          : Oscillator Frequency"""

        setting = '/%s/pids/%d/input' % (self.dev_ID, pid_index-1)
        dic = yield self.daq.get(setting,True)
        sig_ind = int(dic[setting])
        returnValue(sig_ind)

    @setting(1860, pid_index = 'i', signal_chn = 'i', returns = '')
    def set_pid_input_channel(self, c, pid_index, signal_chn):
        """Set the PID Input Signal (1 through 4) to the specified channel. If the input signal
        is currently set to a demodulator, this corresponds to the demodulator index. If it's
        set to aux, it's the aux input number. Etc..."""

        setting = ['/%s/pids/%d/inputchannel' % (self.dev_ID, pid_index-1), signal_chn-1],
        yield self.daq.set(setting)

    @setting(1870, pid_index = 'i', returns = 'i')
    def get_pid_input_channel(self, c, pid_index):
        """Get the PID Input Signal (1 through 4) channel. If the input signal
        is currently set to a demodulator, this corresponds to the demodulator index. If it's
        set to aux, it's the aux input number. Etc..."""

        setting = '/%s/pids/%d/inputchannel' % (self.dev_ID, pid_index-1)
        dic = yield self.daq.get(setting,True)
        sig_chn = int(dic[setting])+1
        returnValue(sig_chn)

    @setting(188, pid_index = 'i', setpoint = 'v[]', returns = '')
    def set_pid_setpoint(self, c, pid_index, setpoint):
        """Sets the PID (1 through 4) setpoint."""

        setting = ['/%s/pids/%d/setpoint' % (self.dev_ID, pid_index-1), setpoint],
        yield self.daq.set(setting)

    @setting(189, pid_index = 'i', returns = 'v[]')
    def get_pid_setpoint(self, c, pid_index):
        """Gets the PID (1 through 4) setpoint."""
        setting = '/%s/pids/%d/setpoint' % (self.dev_ID, pid_index-1)
        dic = yield self.daq.get(setting,True)
        setpoint = float(dic[setting])
        returnValue(setpoint)

    @setting(190, pid_index = 'i', signal_index = 'i', returns = '')
    def set_pid_output_signal(self, c, pid_index, signal_index):
        """Set the PID Output Signal (1 through 4).
        Signal index: Corresponding Signal
         0          : Output 1 Amplitude (This requires output channel to be set to 7)
         1          : Output 2 Amplitude (This requires output channel to be set to 8)
         2          : Oscillator Frequency
         3          : Aux Output Offset
         4          : DIO (int16)"""

        setting = ['/%s/pids/%d/output' % (self.dev_ID, pid_index-1), signal_index],
        yield self.daq.set(setting)

    @setting(191, pid_index = 'i', returns = 'i')
    def get_pid_output_signal(self, c, pid_index):
        """Get the PID Output Signal (1 through 4).
        Signal index: Corresponding Signal
         0          : Output 1 Amplitude (This requires output channel to be set to 6)
         1          : Output 2 Amplitude (This requires output channel to be set to 7)
         2          : Oscillator Frequency
         3          : Aux Output Offset
         4          : DIO (int16)"""

        setting = '/%s/pids/%d/output' % (self.dev_ID, pid_index-1)
        dic = yield self.daq.get(setting,True)
        sig_chn = int(dic[setting])
        returnValue(sig_chn)

    @setting(192, pid_index = 'i', signal_chn = 'i', returns = '')
    def set_pid_output_channel(self, c, pid_index, signal_chn):
        """Set the PID Output Signal (1 through 4) to the specified channel. If the output signal
        is currently set to oscillator frequency, this corresponds to the oscillator index (1 or 2). If
        set to Aux Output Offset, this corresponds to the aux output number. If signal is set to output
        1 amplitude, this must be set to 6. output 2 amplitude should have this set to 7. And DIO (int16)
        should have this set to 1."""

        setting = ['/%s/pids/%d/outputchannel' % (self.dev_ID, pid_index-1), signal_chn-1],
        yield self.daq.set(setting)

    @setting(193, pid_index = 'i', returns = 'i')
    def get_pid_output_signal(self, c, pid_index):
        """Set the PID Output Signal (1 through 4) channel."""
        setting = '/%s/pids/%d/outputchannel' % (self.dev_ID, pid_index-1)
        dic = yield self.daq.get(setting,True)
        sig_chn = int(dic[setting])+1
        returnValue(sig_chn)

    @setting(194, pid_index = 'i', center = 'v[]', returns = '')
    def set_pid_output_center(self, c, pid_index, center):
        """Set the PID Output (1 through 4) Signal center."""
        setting = ['/%s/pids/%d/center' % (self.dev_ID, pid_index-1), center],
        yield self.daq.set(setting)

    @setting(195, pid_index = 'i', returns = 'v[]')
    def get_pid_output_center(self, c, pid_index):
        """Gets the PID Output (1 through 4) signal center."""
        setting = '/%s/pids/%d/center' % (self.dev_ID, pid_index-1)
        dic = yield self.daq.get(setting,True)
        center = float(dic[setting])
        returnValue(center)

    @setting(196, pid_index = 'i', range = 'v[]', returns = '')
    def set_pid_output_range(self, c, pid_index, range):
        """Set the PID Output (1 through 4) signal range. Full range is center - range to center + range."""
        setting = ['/%s/pids/%d/range' % (self.dev_ID, pid_index-1), range],
        yield self.daq.set(setting)

    @setting(197, pid_index = 'i', returns = 'v[]')
    def get_pid_output_range(self, c, pid_index):
        """Gets the PID Output (1 through 4) signal range. Full range is center - range to center + range."""
        setting = '/%s/pids/%d/range' % (self.dev_ID, pid_index-1)
        dic = yield self.daq.get(setting,True)
        center = float(dic[setting])
        returnValue(center)

    @setting(198, pid_index = 'i', P = 'v[]', returns = '')
    def set_pid_p(self, c, pid_index, P):
        """Set the PID (1 through 4) proportional term."""
        setting = ['/%s/pids/%d/p' % (self.dev_ID, pid_index-1), P],
        yield self.daq.set(setting)

    @setting(199, pid_index = 'i', returns = 'v[]')
    def get_pid_p(self, c, pid_index):
        """Gets the PID (1 through 4) proportional term."""
        setting = '/%s/pids/%d/p' % (self.dev_ID, pid_index-1)
        dic = yield self.daq.get(setting,True)
        p = float(dic[setting])
        returnValue(p)

    @setting(200, pid_index = 'i', I = 'v[]', returns = '')
    def set_pid_i(self, c, pid_index, I):
        """Set the PID (1 through 4) integral term."""
        setting = ['/%s/pids/%d/i' % (self.dev_ID, pid_index-1), I],
        yield self.daq.set(setting)

    @setting(201, pid_index = 'i', returns = 'v[]')
    def get_pid_i(self, c, pid_index):
        """Gets the PID (1 through 4) integral term."""
        setting = '/%s/pids/%d/i' % (self.dev_ID, pid_index-1)
        dic = yield self.daq.get(setting,True)
        i = float(dic[setting])
        returnValue(i)

    @setting(202, pid_index = 'i', D = 'v[]', returns = '')
    def set_pid_d(self, c, pid_index, D):
        """Set the PID (1 through 4) derivative term."""
        setting = ['/%s/pids/%d/d' % (self.dev_ID, pid_index-1), D],
        yield self.daq.set(setting)

    @setting(203, pid_index = 'i', returns = 'v[]')
    def get_pid_d(self, c, pid_index):
        """Gets the PID (1 through 4) derivative term."""
        setting = '/%s/pids/%d/d' % (self.dev_ID, pid_index-1)
        dic = yield self.daq.get(setting,True)
        d = float(dic[setting])
        returnValue(d)

    @setting(2020, pid_index = 'i', on = 'b', returns = '')
    def set_pid_on(self, c, pid_index, on):
        """Enable the PID if on is True, disable it if on is False."""
        setting = ['/%s/pids/%d/enable' % (self.dev_ID, pid_index-1), on],
        yield self.daq.set(setting)

    @setting(2030, pid_index = 'i', returns = 'b')
    def get_pid_on(self, c, pid_index):
        """Returns True if the PID is on, False if the PID is off."""
        setting = '/%s/pids/%d/enable' % (self.dev_ID, pid_index-1)
        dic = yield self.daq.get(setting,True)
        d = bool(dic[setting])
        returnValue(d)

#------------------------------------------------------------------------------------------------------------------------------------------#
    """
    The following section of code has all of the commands relevant to polling data. Most of the data reading happens in this section.
    This allows you to probe data that being read quickly by the Zurich lock in. Poll data will update the server polled data variable
    with a dictionary containing the data to all the subscribed paths. Ie, if you're interested in the data coming from the PLL, you
    need to subscribe to the PLL, then poll the data. Then, use the functions to extract the desired data from the polled data dictionary.
    """

    @setting(501, rec_time= 'v[]', timeout = 'i', returns = '')
    def poll_data(self,c, rec_time, timeout):
        """This function returns the data previously in the API's buffers or
        obtained during the specified time. It only returns data of subscribed
        channels. This function blocks until the recording time is
        elapsed. Recording time input is in seconds. Timeout time input is in
        milliseconds. Recommended timeout value is 500ms. Below is an example of code:

        cxn = labrad.connect() \n
        hf = cxn.hf2li_server \n
        hf.detect_devices() \n
        hf.select_device() \n
        hf.subscribe_PLL(1) \n
        #Sync clears the buffer and ensures all the settings are set before continuing \n
        hf.sync() \n
        hf.poll_data(0.1, 500) \n
        freq = hf.polled_PLL_freqdelta(1) \n
        """

        self.poll_data = yield self.daq.poll(rec_time, timeout, 1, True)
        print(self.poll_data)

    @setting(502, PLL_index = 'i', returns = '')
    def subscribe_pll(self, c, PLL_index):
        """Subscribes the poll command to the outputs of the PLL with the provided index. This includes the
        PLL freqdelta, PLL error, and the PLL locked parameter (not working)."""
        path = '/%s/plls/%d/*' % (self.dev_ID, PLL_index-1)
        yield self.daq.subscribe(path)

    @setting(503, PLL_index = 'i', returns = '')
    def unsubscribe_pll(self, c, PLL_index):
        """Subscribes the poll command to the outputs of the PLL with the provided index."""
        path = '/%s/plls/%d/*' % (self.dev_ID, PLL_index-1)
        yield self.daq.unsubscribe(path)

    @setting(504, PLL_index = 'i', returns = '*v[]')
    def polled_pll_freqdelta(self, c, PLL_index):
        """Returns the data Subscribes the poll command to the outputs of the PLL with the provided index."""
        path = '/%s/plls/%d/freqdelta' % (self.dev_ID, PLL_index-1)
        try:
            freqdelta = yield self.poll_data[path]
        except:
            freqdelta = []
        returnValue(freqdelta)

    @setting(505, PLL_index = 'i', returns = '*v[]')
    def polled_pll_error(self, c, PLL_index):
        """Returns the data Subscribes the poll command to the outputs of the PLL with the provided index."""
        path = '/%s/plls/%d/error' % (self.dev_ID, PLL_index-1)
        try:
            error = yield self.poll_data[path]
        except:
            error = []
        returnValue(error)

    #Currently doesn't work, tbd if fixable
    @setting(5050, PLL_index = 'i', returns = '*v[]')
    def polled_pll_lock(self, c, PLL_index):
        """Returns the data Subscribes the poll command to the outputs of the PLL with the provided index."""
        path = '/%s/plls/%d/locked' % (self.dev_ID, PLL_index-1)
        try:
            error = yield self.poll_data[path]
        except:
            error = []
        returnValue(error)

    @setting(506, aux_out_index = 'i', returns = '')
    def subscribe_aux_out(self, c, aux_out_index):
        """Subscribes the poll command to the outputs of the Auxiliary Output with the provided index. CURRENLTY NOT FUNCTIONAL"""
        path = '/%s/auxouts/%d/value' % (self.dev_ID, aux_out_index-1)
        yield self.daq.subscribe(path)

    @setting(507, aux_out_index = 'i', returns = '')
    def unsubscribe_aux_out(self, c, aux_out_index):
        """Subscribes the poll command to the outputs of the Auxiliary Output with the provided index. CURRENLTY NOT FUNCTIONAL"""
        path = '/%s/auxouts/%d/value' % (self.dev_ID, aux_out_index-1)
        yield self.daq.unsubscribe(path)

    @setting(508, aux_out_index = 'i', returns = '*v[]')
    def polled_aux_out(self, c, aux_out_index):
        """Returns the data Subscribes the poll command to the outputs of the PLL with the provided index. CURRENLTY NOT FUNCTIONAL"""
        path = '/%s/auxouts/%d/value' % (self.dev_ID, aux_out_index-1)
        try:
            aux_out = yield self.poll_data[path]
        except:
            aux_out = []
        returnValue(aux_out)

#------------------------------------------------------------------------------------------------------------------------------------------#
    """
    Additional functions that may be useful for programming the server.
    """

    def sleep(self,secs):
        """Asynchronous compatible sleep command. Sleeps for given time in seconds, but allows
        other operations to be done elsewhere while paused."""
        d = defer.Deferred()
        reactor.callLater(secs,d.callback,'Sleeping')
        return d

__server__ = HF2LIServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
