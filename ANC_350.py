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

#  This server was adaped from PyANC350v4
#  PyANC350v4 is a control scheme suitable for the Python coding style
#    for the attocube ANC350 closed-loop positioner system.
#
#  It implements ANC350v4lib, which in turn depends on anc350v4.dll and libusb0.dll, which are provided by attocube in the
#     ANC350_Library folder on the driver disc. Place all of these in a folder in the same directory as the server, in 
#     addition to ANC350libv4.py. Note that the drivers for communicating with the ANC350 also need to be installed separately. 
#
#  At present this only addresses the first ANC350 connected to the
#    machine.
#
#  For tidiness remember to disconnect the server when finished, as the ANC350 only permits one connection at a time. 
#
#                PyANC350 is written by Rob Heath
#                      rob@robheath.me.uk
#                         24-Feb-2015
#                       robheath.me.uk
#
#                 PyANC350v4 by Brian Schaefer
#                      bts72@cornell.edu
#                         5-Jul-2016
#              http://nowack.lassp.cornell.edu/
# 
#                   ANC350 LabRAD Server by Marec Serlin
#                       marecserlin@gmail.com
#                         1-Jan-2019

"""
### BEGIN NODE INFO
[info]
name = ANC350 Server
version = 0.1
description = Communicates with the ANC350 which controls the Attocube ANPx/z101 piezo coarse positioners.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad.server import LabradServer, setting
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as units
from labrad.types import Value
import sys
import ctypes

path = sys.path[0]
sys.path.append(path + r'\ANC350')

import ANC350libv4 as ANC

class ANC350Server(LabradServer):
    name = "ANC350 Server"    # Will be labrad name of server
    
    def initServer(self):  # Do initialization here
        self.device = None
        
    @setting(100, devNo = 'i', returns = '')
    def connect(self, c, devNo=0):
        '''
        Initializes and connects the selected device. This has to be done before any access to control variables or measured data.

        Parameters
            devNo	Sequence number of the device. Must be smaller than the devCount from the last ANC_discover call. Default: 0
        Returns
            device	Handle to the opened device, NULL on error
        '''
        
        device = ctypes.c_void_p()
        yield ANC.connect(devNo, ctypes.byref(device))
        self.device = device
        
    @setting(101,returns = '')
    def disconnect(self, c):
        '''
        Closes the connection to the device. The device handle becomes invalid.

        Parameters
            None
        Returns
            None
        '''
        
        yield ANC.disconnect(self.device)
       
    @setting(102, ifaces = 'i', returns = 'i')
    def discover(self, c, ifaces=3):
        '''
        The function searches for connected ANC350RES devices on USB and LAN and initializes internal data structures per device. Devices that are in use by another application or PC are not found. The function must be called before connecting to a device and must not be called as long as any devices are connected.

        The number of devices found is returned. In subsequent functions, devices are identified by a sequence number that must be less than the number returned.

        Parameters
            ifaces	Interfaces where devices are to be searched. {None: 0, USB: 1, ethernet: 2, all:3} Default: 3
        Returns
            devCount	number of devices found
        '''
        devCount = ctypes.c_int()
        yield ANC.discover(ifaces, ctypes.byref(devCount))
        returnValue(devCount.value)
    
    
    @setting(103, axisNo = 'i', enable = 'b', resolution = 'v[]', returns = '')
    def configure_aquadb_in(self, c, axisNo, enable, resolution):
        '''
        Enables and configures the A-Quad-B (quadrature) input for the target position.
        Parameters
            axisNo	Axis number (0 ... 2)
            enable	Enable (1) or disable (0) A-Quad-B input
            resolution	A-Quad-B step width in m. Internal resolution is 1 nm.
        Returns
            None
        '''
        yield ANC.configureAQuadBIn(self.device, axisNo, enable, ctypes.c_double(resolution))
        
    @setting(104, axisNo = 'i', enable = 'b', resolution = 'v[]', clock = 'v[]', returns = '')
    def configure_aquadb_out(self, c, axisNo, enable, resolution, clock):
        '''
        Enables and configures the A-Quad-B output of the current position.

        Parameters
            axisNo	Axis number (0 ... 2)
            enable	Enable (1) or disable (0) A-Quad-B output
            resolution	A-Quad-B step width in m; internal resolution is 1 nm
            clock	Clock of the A-Quad-B output [s]. Allowed range is 40ns ... 1.3ms; internal resulution is 20ns.
        Returns/
            None
        '''
        yield ANC.configureAQuadBOut(self.device, axisNo, enable, ctypes.c_double(resolution), ctypes.c_double(clock))
       
    @setting(105, axisNo = 'i', mode = 'i', returns = '')
    def configure_ext_trigger(self, c, axisNo, mode):
        '''
        Enables the input trigger for steps.

        Parameters
            axisNo	Axis number (0 ... 2)
            mode	Disable (0), Quadratur (1), Trigger(2) for external triggering
        Returns
            None
        '''
        yield ANC.configureExtTrigger(self.device, axisNo, mode)
     
    @setting(106, enable = 'b', returns = '')
    def configure_nsl_trigger(self, c, enable):
        '''
        Enables NSL Input as Trigger Source.

        Parameters
            enable	disable(0), enable(1)
        Returns
            None
        '''
        yield ANC.configureNslTrigger(self.device, enable)
    
    @setting(107, axisNo = 'i', returns = '')
    def configure_nsl_trigger_axis(self, c, axisNo):
        '''
        Selects Axis for NSL Trigger.

        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            None
        '''
        yield ANC.configureNslTriggerAxis(self.device, axisNo)
      
    @setting(108, axisNo = 'i', lower = 'v[]', upper = 'v[]', returns = '')
    def configure_rng_trigger(self, c, axisNo, lower, upper):
        '''
        Configure lower position for range Trigger.

        Parameters
            axisNo	Axis number (0 ... 2)
            lower	Lower position for range trigger (nm)
            upper	Upper position for range trigger (nm)
        Returns
            None
        '''
        yield ANC.configureRngTrigger(self.device, axisNo, lower, upper)
       
    @setting(109, axisNo = 'i', epsilon = 'v[]', returns = '')
    def configure_rng_trigger_eps(self, c, axisNo, epsilon):
        '''
        Configure hysteresis for range Trigger.

        Parameters
            axisNo	Axis number (0 ... 2)
            epsilon	hysteresis in nm / mdeg
        Returns
            None
        '''
        yield ANC.configureRngTriggerEps(self.device, axisNo, epsilon)
        
    @setting(110, axisNo = 'i', polarity = 'i', returns = '')
    def configure_rng_trigger_pol(self, c, axisNo, polarity):
        '''
        Configure lower position for range Trigger.

        Parameters
            axisNo	Axis number (0 ... 2)
            polarity	Polarity of trigger signal when position is between lower and upper Low(0) and High(1)
        Returns
            None
        '''
        yield ANC.configureRngTriggerPol(self.device, axisNo, polarity)
       
    @setting(111, axisNo ='i', returns='s')
    def get_actuator_name(self, c, axisNo):
        '''
        Get the name of the currently selected actuator

        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            name	Name of the actuator
        '''
        name = ctypes.create_string_buffer(20)
        yield ANC.getActuatorName(self.device, axisNo, ctypes.byref(name))
        returnValue(name.value.decode('utf-8'))
        
    @setting(112, axisNo ='i', returns='i')
    def get_actuator_type(self, c, axisNo):
        '''
        Get the type of the currently selected actuator

        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            type_	Type of the actuator {0: linear, 1: goniometer, 2: rotator}
        '''
        type_ = ctypes.c_int()
        yield ANC.getActuatorType(self.device, axisNo, ctypes.byref(type_))
        returnValue(type_.value)
       
    @setting(113, axisNo ='i', returns='v[]')
    def get_amplitude(self, c, axisNo):
        '''
        Reads back the amplitude parameter of an axis.
        
        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            amplitude	Amplitude V
        '''
        amplitude = ctypes.c_double()
        yield ANC.getAmplitude(self.device, axisNo, ctypes.byref(amplitude))
        returnValue(amplitude.value)
    
    @setting(114, axisNo ='i', returns='*i')
    def get_axis_status(self, c, axisNo):
        '''
        Reads status information about an axis of the device.

        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            connected	Output: If the axis is connected to a sensor.
            enabled	Output: If the axis voltage output is enabled.
            moving	Output: If the axis is moving.
            target	Output: If the target is reached in automatic positioning
            eotFwd	Output: If end of travel detected in forward direction.
            eotBwd	Output: If end of travel detected in backward direction.
            error	Output: If the axis' sensor is in error state.
        '''
        connected = ctypes.c_int()
        enabled = ctypes.c_int()
        moving = ctypes.c_int()
        target = ctypes.c_int()
        eotFwd = ctypes.c_int()
        eotBwd = ctypes.c_int()
        error = ctypes.c_int()
        yield ANC.getAxisStatus(self.device, axisNo, ctypes.byref(connected), ctypes.byref(enabled), ctypes.byref(moving), ctypes.byref(target), ctypes.byref(eotFwd), ctypes.byref(eotBwd), ctypes.byref(error))
        returnValue([connected.value, enabled.value, moving.value, target.value, eotFwd.value, eotBwd.value, error.value])
    
    @setting(115, returns='*i')
    def get_device_config(self, c):
        '''
        Reads static device configuration data

        Parameters
            None
        Returns
            featureSync	"Sync": Ethernet enabled (1) or disabled (0)
            featureLockin	"Lockin": Low power loss measurement enabled (1) or disabled (0)
            featureDuty	"Duty": Duty cycle enabled (1) or disabled (0)
            featureApp	"App": Control by IOS app enabled (1) or disabled (0)
        '''
        features = ctypes.c_int()
        yield ANC.getDeviceConfig(self.device, features)
        
        featureSync = 0x01&features.value
        featureLockin = (0x02&features.value)/2
        featureDuty = (0x04&features.value)/4
        featureApp = (0x08&features.value)/8
        
        returnValue([featureSync, featureLockin, featureDuty, featureApp])

    #This function is commented out because it returns a list of different datatypes that I don't know how to make compatible with LabRAD 
    #datatypes (ie. specifying the correct return variables in the @setting header). Otherwise, the function works
    # @setting(116, devNo = 'i', returns = '*?')
    # def get_device_info(self, c, devNo=0):
        # '''
        # Returns available information about a device. The function can not be called before ANC_discover but the devices don't have to be connected . All Pointers to output parameters may be zero to ignore the respective value.

        # Parameters
            # devNo	Sequence number of the device. Must be smaller than the devCount from the last ANC_discover call. Default: 0
        # Returns
            # devType	Output: Type of the ANC350 device. {0: Anc350Res, 1:Anc350Num, 2:Anc350Fps, 3:Anc350None}
            # id	Output: programmed hardware ID of the device
            # serialNo	Output: The device's serial number. The string buffer should be NULL or at least 16 bytes long.
            # address	Output: The device's interface address if applicable. Returns the IP address in dotted-decimal notation or the string "USB", respectively. The string buffer should be NULL or at least 16 bytes long.
            # connected	Output: If the device is already connected
        # '''
        # devType = ctypes.c_int()
        # id_ = ctypes.c_int()
        # serialNo = ctypes.create_string_buffer(16) 
        # address = ctypes.create_string_buffer(16) 
        # connected = ctypes.c_int()

        # yield ANC.getDeviceInfo(devNo, ctypes.byref(devType), ctypes.byref(id_), ctypes.byref(serialNo), ctypes.byref(address), ctypes.byref(connected))
        # returnValue([devType.value, id_.value, serialNo.value.decode('utf-8'), address.value.decode('utf-8'), connected.value])
    
    @setting(117, returns='i')
    def get_firmware_version(self, c):
        '''
        Retrieves the version of currently loaded firmware.

        Parameters
            None
        Returns
            version	Output: Version number
        '''
        version = ctypes.c_int()
        yield ANC.getFirmwareVersion(self.device, ctypes.byref(version))
        returnValue(version.value)
    
    @setting(118, axisNo ='i', returns='v[]')
    def get_frequency(self, c, axisNo):
        '''
        Reads back the frequency parameter of an axis.

        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            frequency	Output: Frequency in Hz
        '''
        frequency = ctypes.c_double()
        yield ANC.getFrequency(self.device, axisNo, ctypes.byref(frequency))
        returnValue(frequency.value)
    
    @setting(119, axisNo ='i', returns='v[]')
    def get_position(self, c, axisNo):
        '''
        Retrieves the current actuator position. For linear type actuators the position unit is m; for goniometers and rotators it is degree.

        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            position	Output: Current position [m] or [degree]
        '''
        position = ctypes.c_double()
        yield ANC.getPosition(self.device, axisNo, ctypes.byref(position))
        returnValue(position.value)
    
    @setting(120, axisNo ='i', returns='v[]')
    def measure_capacitance(self, c, axisNo):
        '''
        Performs a measurement of the capacitance of the piezo motor and returns the result. If no motor is connected, the result will be 0. The function doesn't return before the measurement is complete; this will take a few seconds of time.

        Parameters
            axisNo	Axis number (0 ... 2)
        Returns
            cap	Output: Capacitance [F]
        '''
        cap = ctypes.c_double()
        yield ANC.measureCapacitance(self.device, axisNo, ctypes.byref(cap))
        returnValue(cap.value)
   
    @setting(121, returns='')
    def save_params(self, c):
        '''
        Saves parameters to persistent flash memory in the device. They will be present as defaults after the next power-on. The following parameters are affected: Amplitude, frequency, actuator selections as well as Trigger and quadrature settings.

        Parameters
            None
        Returns
            None
        '''
        yield ANC.saveParams(self.device)
    
    @setting(122, axisNo ='i', actuator ='i', returns='')
    def select_actuator(self, c, axisNo, actuator):
        '''
        Selects the actuator to be used for the axis from actuator presets.

        Parameters
            axisNo	Axis number (0 ... 2)
            actuator	Actuator selection (0 ... 255)
                0: ANPx51
                1: ANPz51
                2: ANPz51ext
                3: ANPx101
                4: ANPz101
                5: ANPz102
                6: ANPz101ext
                7: ANPz111(ext)
                8: ANPx111(ext)
                9: ANPx121
                10: ANPx311
                11: ANPx321
                12: ANPx341
                13: ANGt101
                14: ANGp101
                15: ANR(v)101
                16: ANR(v)5*
                17: ANR(v)200/240
                18: ANR(v)220
                19: Test
        Returns
            None
        '''
        yield ANC.selectActuator(self.device, axisNo, actuator)
    
    @setting(123, axisNo ='i', amplitude ='v[]', returns='')
    def set_amplitude(self, c, axisNo, amplitude):
        '''
        Sets the amplitude parameter for an axis

        Parameters
            axisNo	Axis number (0 ... 2)
            amplitude	Amplitude in V, internal resolution is 1 mV
        Returns
            None
        '''
        yield ANC.setAmplitude(self.device, axisNo, ctypes.c_double(amplitude))
   
    @setting(124, axisNo ='i', enable ='b', autoDisable = 'b', returns='')
    def set_axis_output(self, c, axisNo, enable, autoDisable):
        '''
        Enables or disables the voltage output of an axis.

        Parameters
            axisNo	Axis number (0 ... 2)
            enable	Enables (1) or disables (0) the voltage output.
            autoDisable	If the voltage output is to be deactivated automatically when end of travel is detected.
        Returns
            None
        '''
        yield ANC.setAxisOutput(self.device, axisNo, enable, autoDisable)
   
    @setting(125, axisNo ='i', voltage ='v[]', returns='')
    def set_dc_voltage(self, c, axisNo, voltage):
        '''
        Sets the DC level on the voltage output when no sawtooth based motion is active.

            Parameters
            axisNo	Axis number (0 ... 2)
            voltage	DC output voltage [V], internal resolution is 1 mV
        Returns
            None        
        '''
        yield ANC.setDcVoltage(self.device, axisNo, ctypes.c_double(voltage))
 
    @setting(126, axisNo ='i', frequency ='v[]', returns='')
    def set_frequency(self, c, axisNo, frequency):
        '''
        Sets the frequency parameter for an axis

        Parameters
            axisNo	Axis number (0 ... 2)
            frequency	Frequency in Hz, internal resolution is 1 Hz
        Returns
            None
        '''
        yield ANC.setFrequency(self.device, axisNo, ctypes.c_double(frequency))
        
    @setting(127, axisNo ='i', target ='v[]', returns='')
    def set_target_position(self, c, axisNo, target):
        '''
        Sets the target position for automatic motion, see ANC_startAutoMove. For linear type actuators the position unit is m, for goniometers and rotators it is degree.

        Parameters
            axisNo	Axis number (0 ... 2)
            target	Target position [m] or [degree]. Internal resulution is 1 nm or 1 microdegree.
        Returns
            None
        '''
        yield ANC.setTargetPosition(self.device, axisNo, ctypes.c_double(target))
        
    @setting(128, axisNo ='i', targetRg ='v[]', returns='')
    def set_target_range(self, c, axisNo, targetRg):
        '''
        Defines the range around the target position where the target is considered to be reached.

        Parameters
            axisNo	Axis number (0 ... 2)
            target	Target position [m] or [degree]. Internal resulution is 1 nm or 1 microdegree.
        Returns
            None
        '''
        yield ANC.setTargetRange(self.device, axisNo, ctypes.c_double(targetRg))
        
    @setting(1280, axisNo ='i', targetGround = 'b', returns='')
    def set_target_ground(self, c, axisNo, targetGround):
        '''
        Defines the range around the target position where the target is considered to be reached.

        Parameters
            axisNo	Axis number (0 ... 2)
            target	Target position [m] or [degree]. Internal resulution is 1 nm or 1 microdegree.
        Returns
            None
        '''
        yield ANC.setTargetGround(self.device, axisNo, targetGround)
        
    @setting(129, axisNo ='i', enable ='b', relative ='b', returns='')
    def start_auto_move(self, c, axisNo, enable, relative):
        '''
        Switches automatic moving (i.e. following the target position) on or off

        Parameters
            axisNo	Axis number (0 ... 2)
            enable	Enables (1) or disables (0) automatic motion
            relative	If the target position is to be interpreted absolute (0) or relative to the current position (1)
        Returns
            None
        '''
        yield ANC.startAutoMove(self.device, axisNo, enable, relative)
        
    @setting(130, axisNo ='i', start ='b', backward ='b', returns='')
    def start_continuous_move(self, c, axisNo, start, backward):
        '''
        Starts or stops continous motion in forward direction. Other kinds of motions are stopped.

        Parameters
            axisNo	Axis number (0 ... 2)
            start	Starts (1) or stops (0) the motion
            backward	If the move direction is forward (0) or backward (1)
        Returns
            None
        '''
        yield ANC.startContinousMove(self.device, axisNo, start, backward)
        
    @setting(131, axisNo ='i', backward ='b', returns='')
    def start_single_step(self, c, axisNo, backward):
        '''
        Triggers a single step in desired direction.

        Parameters
            axisNo	Axis number (0 ... 2)
            backward	If the step direction is forward (0) or backward (1)
        Returns
            None
        '''
        yield ANC.startSingleStep(self.device, axisNo, backward)
        
__server__ = ANC350Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)