"""In addition, you must be on the units home screen (not the menu) to successfully enter remote mode.
"""


"""
### BEGIN NODE INFO
[info]
name = lm_510
version = 1.0
description = LM-510 Liquid Cryogen Level Monitor Server
[startup]
cmdline = %PYTHON% %FILE%
timeout = 20
[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

import platform
global serial_server_name
serial_server_name = (platform.node() + '_serial_server').replace('-','_').lower()

from labrad.server import setting,Signal
from labrad.devices import DeviceServer,DeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as units
from labrad.types import Value
import time
import re

TIMEOUT = Value(5,'s')
BAUD = 9600 
BYTESIZE = 8
STOPBITS = 1
PARITY = None

possible_unit_letters = '%incm'


class serverInfo(object):
    def __init__(self):
        self.deviceName = 'Cryomagnetics,LM-510,6983,2.12'
        self.serverName = 'lm_510'

    def getDeviceName(self,comPort):
        return "%s (%s)"%(self.serverName,comPort)



class lm_510Wrapper(DeviceWrapper):

    @inlineCallbacks
    def connect(self, server, port):
        """Connect to a device."""
        print('connecting to "%s" on port "%s"...' % (server.name, port), end=' ')
        self.server = server
        self.ctx = server.context()
        self.port = port
        p = self.packet()
        p.open(port)
        p.baudrate(BAUD)
        p.bytesize(BYTESIZE)
        p.stopbits(STOPBITS)
        p.setParity = PARITY
        p.read() #clear out the read buffer
        p.timeout(TIMEOUT)
        print("Connected")
        yield p.send()


    def shutdown(self):
        """Disconnect from the serial port when we shut down."""
        return self.packet().close().send()

    def packet(self):
        """Create a packet in our private context."""
        return self.server.packet(context=self.ctx)

    @inlineCallbacks
    def read(self):
        p=self.packet()
        p.read_line()
        ans=yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def write(self, code):
        """Write a data value to the heat switch."""
        yield self.packet().write(code).send()

    @inlineCallbacks
    def query(self, code):
        """ Write, then read. """
        p = self.packet()
        yield p.write_line(code).send()
        yield p.read_line().send()
        #returnValue(ans.read_line)




class lm_510Server(DeviceServer):
    name = 'lm_510'
    deviceName = 'Cryomagnetics,LM-510,6983,2.12'
    deviceWrapper = lm_510Wrapper

    @inlineCallbacks
    def initServer(self):
        print('loading config info...', end=' ')
        self.reg = self.client.registry()
        yield self.loadConfigInfo()
        print('done.')
        print(self.serialLinks)
        yield DeviceServer.initServer(self)

    @inlineCallbacks
    def loadConfigInfo(self):
        """Load configuration information from the registry."""
        reg = self.reg
        yield reg.cd(['', 'Servers', 'lm_510', 'Links'], True)
        dirs, keys = yield reg.dir()
        p = reg.packet()
        print(" created packet")
        print("printing all the keys",keys)
        for k in keys:
            print("k=",k)
            p.get(k, key=k)
        ans = yield p.send()
        print("ans=",ans)
        self.serialLinks = dict((k, ans[k]) for k in keys)

    @inlineCallbacks
    def findDevices(self):
        """Find available devices from list stored in the registry."""
        devs = []
        print(list(self.serialLinks.items()))
        for name, (serServer, port) in list(self.serialLinks.items()):
            if serServer not in self.client.servers:
                continue
            server = self.client[serServer]
            print(server)
            print(port)
            ports = yield server.list_serial_ports()
            print(ports)
            if port not in ports:
                continue
            devName = '%s - %s' % (serServer, port)
            print(devName, 'this is a devName')
            devs += [(devName, (server, port))]

       # devs += [(0,(3,4))]
        returnValue(devs)

    @setting(100)
    def connect(self,c,server,port):
        dev=self.selectedDevice(c)
        yield dev.connect(server,port)
        
    @setting(2, 'Select Device',
                key=[': Select first device',
                     's: Select device by name',
                     'w: Select device by ID'],
                returns=['s: Name of the selected device'])
    def select_device(self, c, key=0):
        """Select a device for the current context."""
        dev = self.selectDevice(c, key=key)
        yield self.remote()
        return dev.name

    @setting(201, mode = 's')
    def boost(self,c,mode):
        """
        Availabe Mode: ON, OFF, SMART
        The BOOST command sets the operating mode for the boost portion of a sensor read cycle.
        BOOST OFF will eliminate the boost portion of the read cycle, BOOST ON enables the boost portion on every read cycle, and BOOST SMART enables a boost cycle if no readings have been taken in the previous 5 minutes.
        """
        dev = self.selectedDevice(c)
        yield dev.write("BOOST %s\r" %mode)
        yield dev.read()

    @setting(202, returns = 's')
    def get_boost_mode(self,c):
        """
        Get operating mode for the boost portion of a sensor read cycle.
        BOOST OFF will eliminate the boost portion of the read cycle, BOOST ON enables the boost portion on every read cycle, and BOOST SMART enables a boost cycle if no readings have been taken in the previous 5 minutes.
        """
        dev=self.selectedDevice(c)
        yield dev.write("BOOST?\r")
        yield dev.read()
        ans = yield dev.read()
        returnValue(ans)

    @setting(203, mode = 's')
    def control_mode(self, c, mode):
        """
        Availabe Mode: AUTO, OFF, MANUAL
        Set the control mode of the channel to the selected mode.
        """
        dev = self.selectedDevice(c)
        yield dev.write("CTRL %s\r" %mode)
        yield dev.read()


    @setting(204, returns = 's')
    def get_control_mode(self, c):
        """
        Returns the status of the Control Relay (i.e., refill status) if the Control Relay is not already active, or the time in minutes since CTRL started if the Control Relay is active.
        "Off" indicates that a Ctrl Timeout has not occurred.
        "Timeout" indicates that the Ctrl High limit was not reached before the Timeout time was exceeded, and that Control Relay is inhibited until the operator resets the Ctrl Timeout by selecting MENU on the LM-510 or issuing a *RST command via the computer interface.
        The Timeout can be inhibited by setting the value to zero in the Ctrl Menu for the channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write("CTRL?1\r")
        yield dev.read()
        ans = yield dev.read()
        returnValue(ans)

    @setting(205, mode = 's')
    def error_mode(self, c, mode):
        """
        Availabe Mode: 0, 1
        Set the error responce mode of the channel to the selected mode.
        0 - diable error reporting
        1 - enable error reporting
        """
        dev = self.selectedDevice(c)
        yield dev.write("ERROR %s\r" %mode)
        yield dev.read()

    @setting(206, returns = 's')
    def get_error_mode(self, c):
        """
        Query the selected error reporting mode.
        0 - diable error reporting
        1 - enable error reporting
        """
        dev = self.selectedDevice(c)
        yield dev.write("ERROR?\r")
        resp = yield dev.read()
        ans = yield dev.read()
        returnValue(ans)

    @setting(207,thresh = 'v[]')
    def set_high_alarm_threshold(self, c, thresh):
        """
        Availabe Range: 0.0 to Sensor Length
        Set the threshold for the high alarm in the present units for the selected channel.
        If the liquid level rises above the threshold the alarm will be activated.
        The alarm will be disabled if the threshold is set to 100.0.
        """
        dev = self.selectedDevice(c)
        yield dev.write("H-ALM %f\r" %thresh)
        yield dev.read()

    @setting(208, returns = 's') 
    def get_high_alarm_threshold(self,c):
        """
        Query the high alarm threshold in the present units for the selected channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write("H-ALM?\r")
        yield dev.read()
        ans= yield dev.read()
        returnValue(ans)

    @setting(209, thresh = 'v[]')
    def set_high_threshold_control(self,c,thresh):
        """
        Availabe Range: 0.0 to Sensor Length
        Set the high threshold for CTRL functions such as automated LM-510 Operating Instruction Manual - Version 1.2 refill completion.
        The present units for the selected channel are implied.
        A CTRL (refill) cycle is started when a reading is taken that is below the LOW limit.
        A CTRL (refill) cycle is completed when a reading is taken that is above the HIGH limit, or when the Ctrl Timeout configured in the CTRL menu is exceeded.
        A sensor is sampled as in continuous mode during CTRL, but when the HIGH limit is reach the selected sample interval will be used for future readings.
        """
        dev=self.selectedDevice(c)
        yield dev.write("HIGH %f\r" %thresh)
        yield dev.read()

    @setting(210, returns = 's')
    def get_high_threshold_control(self,c):
        """
        Query the high threshold for Control functions (automated refill completion) in the present units for the selected channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write("HIGH?\r")
        yield dev.read()
        ans = yield dev.read()
        returnValue(ans)

    @setting(211, intv = 's')
    def set_sample_interval(self, c, intv):
        """
        Availabe Range: 00:00:00 to 99:59:59
        Set the time between samples for the selected Liquid Helium Level Meter channel.
        Time is in hours, minutes, and seconds.
        """
        dev=self.selectedDevice(c)
        yield dev.write("INTVL %s\r" %intv)
        yield dev.read()

    @setting(212, returns = 's')
    def get_sample_interval(self,c):
        """
        Query the time between samples for the selected Liquid Helium Level Meter channel.
        Time is in hours, minutes, and seconds.
        """
        dev=self.selectedDevice(c)
        yield dev.write("INTVL?\r")
        yield dev.read()
        ans = yield dev.read()
        returnValue(ans)

    @setting(213, thresh = 'v[]')
    def set_low_alarm_threshold(self,c,thresh):
        """
        Availabe Range: 0.0 to Sensor Length
        Set the threshold for the low alarm in the present units for the selected channel.
        If the liquid level rises above the threshold the alarm will be activated.
        The alarm will be disabled if the threshold is set to 0.0.
        """
        dev=self.selectedDevice(c)
        yield dev.write("L-ALM %f\r" %thresh)
        yield dev.read()

    @setting(214, returns = 's') 
    def get_low_alarm_threshold(self,c):
        """
        Query the low alarm threshold in the present units for the selected channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write("L-ALM?\r")
        yield dev.read()
        ans = yield dev.read()
        returnValue(ans)

    @setting(215, returns = 's')
    def get_sensor_length(self, c):
        """
        Query the active sensor length in the present units for the selected channel.
        The length is returned in centimeters if percent is the present unit selection.
        """
        dev=self.selectedDevice(c)
        yield dev.write("LNGTH?\r")
        yield dev.read()
        ans = yield dev.read()
        returnValue(ans)

    @setting(216)
    def local(self, c):
        """
        Returns control the front panel keypad after remote control has been selected by the REMOTE or RWLOCK commands.
        """
        dev=self.selectedDevice(c)
        yield dev.write("LOCAL\r" )
        yield dev.read()

    @setting(217, thresh = 'v[]')
    def set_low_threshold_control(self,c,thresh):
        """
        Availabe Range: 0.0 to Sensor Length
        Set the low threshold for Control functions such as automated refill activation.
        The present units for the selected channel are implied.
        A CTRL (refill) cycle is started when a reading is taken that is below the LOW limit.
        The sensor will be sampled in Continuous mode until the HIGH limit is reached.
        A CTRL cycle is completed when a reading is taken that is above the HIGH limit, or when the Ctrl Timeout configured in the CTRL menu is exceeded.
        """
        dev=self.selectedDevice(c)
        yield dev.write("LOW %f\r" %thresh)
        yield dev.read()


    @setting(218, returns = 's')
    def get_high_threshold_control(self,c):
        """
        Query the low threshold for Control functions (automated refill completion) in the present units for the selected channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write("LOW?\r")
        yield dev.read()
        ans = yield dev.read()
        returnValue(ans)

    @setting(219)
    def prep_measure(self, c):
        """
        starts a measurement on the selected channel.
        The DATA READY bit for the selected channel will be set in the status byte returned by the *STB? command when the measurement is complete.
        """
        dev=self.selectedDevice(c)
        yield dev.write("MEAS 1\r" )
        yield dev.read()

    @setting(220, returns = 's') 
    def get_measure(self,c):
        """
        Query latest reading in the present units for the selected channel.
        If a reading for the selected channel is in progress, the previous reading is returned.
        """
        dev=self.selectedDevice(c)
        yield dev.write("MEAS?1\r")
        yield dev.read()
        ans = yield dev.read()
        returnValue(ans)

    @setting(221, mode = 's')
    def set_sample_mode(self,c,mode):
        """
        Availabe Mode: S(Sample/Hold) or C(Continious)
        Set the sample mode for the selected channel.
        In Sample/Hold mode the measurements are taken when a MEAS command is sent via the computer interface, the <Enter> button is pressed on the front panel, or when the delay between samples set by the INTVL command expires.
        The interval timer is reset on each measurement, regardless of source of the measurement request.
        In Continuous mode measurements are taken as frequently as possible.
        The channel will also operate as in continuous mode any time a CTRL (refill) cycle has been activated by the level dropping below the LOW threshold until the CTRL cycle is completed by the HIGH threshold being exceeded or a *RST command.
        """
        dev=self.selectedDevice(c)
        yield dev.write("MODE %s\r" %mode)
        yield dev.read()

    @setting(222, returns = 's')
    def get_mode(self,c):
        """
        Query the sample mode for the previously selected channel.
        The sample mode may have been set by a MODE command or the front panel menu.
        """
        dev=self.selectedDevice(c)
        yield dev.write("MODE?\r")
        yield dev.read()
        ans = yield dev.read()
        returnValue(ans)

    @setting(223)
    def remote(self, c):
        """
        Takes control of the LM-510 via the remote interface. This command MUST be executed before any further commands will be recognized by the LM-510. 
        All LM-510 Operating Instruction Manual - Version 1.2 buttons on the front panel are disabled except the Local button.
        This command will be rejected if the menu system is being accessed via the front panel or if LOCAL has been selected via the Local button on the front panel.
        Pressing the Local button again when the menu is not selected will allow this command to be executed.
        This command is only necessary for RS-232 operation since the IEEE-488 RL1 option provides for bus level control of the Remote and Lock controls.
        """
        dev=self.selectedDevice(c)
        yield dev.write("REMOTE\r" )
        yield dev.read()

    @setting(224, returns = 's')
    def status(self, c):
        """
        Query detailed instrument status as decimal values, and the status of local menu selection.
        When an operator selects the Menu, the instrument is taken out of operate mode, and <Menu Mode> is returned as 1.
        <Menu Mode> is returned as 0 when in operate mode.
        Channel detailed status is returned as a decimal number where each bit indicates a status condition of the channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write("STAT?\r")
        yield dev.read()
        ans = yield dev.read()
        returnValue(ans)

    @setting(225, returns = 'i')
    def channel_type(self, c):
        """
        Query for the channel type of the designated channel.
        0 denotes a liquid helium level sensor and 1 denotes a liquid nitrogen level sensor.
        """
        dev=self.selectedDevice(c)
        yield dev.write("TYPE?1\r")
        yield dev.read()
        ans= yield dev.read()
        returnValue(ans)

    @setting(226, unt = 's')
    def set_units(self, c, unt):
        """
        Availabe Units: CM, IN, PERCENT or %
        Set the units to be used for all input and display operations for the channel.
        Units may be set to centimeters, inches,or percentage of sensor length.
        """
        dev=self.selectedDevice(c)
        yield dev.write("UNITS %s\r" %unt)
        yield dev.read()

    @setting(227, returns = 's')
    def get_units(self,c):
        """
        Query for the units of the designated channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write("UNITS?\r")
        yield dev.read()
        ans = yield dev.read()
        returnValue(ans)

    @setting(228)
    def clear_status(self, c):
        """
        Operates per IEEE Std 488.2-1992 by clearing the Standard Event Status Register (ESR) and resetting the MAV bit in the Status Byte Register (STB).
        """
        dev=self.selectedDevice(c)
        yield dev.write("*CLS\r" )
        yield dev.read()

    @setting(229, mask = 'i')
    def enable_standard_event(self, c, mask):
        """
        Standard Event Status Enable Command
        Availabe Range: 0 to 255
        Operate per IEEE Std 488.2-1992 by setting the specified mask into the Standard Event Status Enable Register (ESE).
        """
        dev=self.selectedDevice(c)
        yield dev.write("*ESE %i\r" %mask)
        yield dev.read()


    @setting(230, returns = '?')
    def query_ESE(self,c):
        """
        Standard Event Status Enable Query
        Operates per IEEE Std 488.2-1992 by returning the mask set in the Standard Event Status Enable Register (ESE) by a prior *ESE command.
        """
        dev=self.selectedDevice(c)
        yield dev.write("*ESE?\r")
        yield dev.read()
        ans = yield dev.read()
        returnValue(ans)

    @setting(231, returns = '?')
    def query_ESR(self,c):
        """
        Standard Event Status Register Query
        Operate per IEEE Std 488.2-1992 by returning the contents of the Standard Event Status Register and then clearing the register.
        """
        dev=self.selectedDevice(c)
        yield dev.write("*ESR?\r")
        yield dev.read()
        ans=yield dev.read()
        returnValue(ans)

    @setting(232, returns='s')
    def idn(self,c):
        """
        Query Idenification
        Operate per IEEE Std 488.2-1992 by returning the LM-510 manufacturer, model, serial number and firmware level.
        """
        dev=self.selectedDevice(c)
        yield dev.write("*IDN?\r")
        yield dev.read()
        ans= yield dev.read()
        returnValue(ans)

    @setting(233)
    def operation_complete(self, c):
        """
        Operation Complete Command
        Operate per IEEE Std 488.2-1992 by placing the Operation Complete message in the Standard Event Status Register (ESR).
        The LM-510 processes each command as it is received and does not defer any commands for later processing.
        """
        dev=self.selectedDevice(c)
        yield dev.write("*OPC\r")
        yield dev.read()


    @setting(234)
    def reset(self, c):
        """
        Operates per IEEE Std 488.2-1992 by returning the LM-510 to its power up configuration.
        This selects channel 1 as the default channel, terminates any control (refill) sequence in progress, and clears any Ctrl Timeouts that may have occurred.
        If the optional parameter <hw> is provided, the instrument will perform a hardware reset one second later instead of returning to power up configuration as required by the Standard.
        """
        dev=self.selectedDevice(c)
        yield dev.write("*RST\r")
        yield dev.read()

    @setting(235, returns = 'v[]')
    def measure(self, c):
        """
        Starts and reads a measurement, then reformats the result (given in the units specified by get_units()) to a float. This combines prep_measure() and get_measure().
        """
        dev=self.selectedDevice(c)
        yield dev.write("MEAS 1\r" )
        yield dev.read()

        yield dev.write("MEAS?1\r")
        yield dev.read()
        ans = yield dev.read()
        ans = float(re.sub('[%incm ]', '', ans))
        returnValue(ans)


    @setting(9001,v='v')
    def do_nothing(self,c,v):
        pass
    @setting(9002)
    def read(self,c):
        dev=self.selectedDevice(c)
        ret=yield dev.read()
        returnValue(ret)
    @setting(9003)
    def write(self,c,phrase):
        dev=self.selectedDevice(c)
        yield dev.write(phrase)
    @setting(9004)
    def query(self,c,phrase):
        dev=self.selectedDevice(c)
        yield dev.write(phrase)
        ret = yield dev.read()
        returnValue(ret)

__server__ = lm_510Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
