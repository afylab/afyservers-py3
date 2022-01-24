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
name = AMI 430
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

from labrad.server import setting
from labrad.devices import DeviceServer,DeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as units
from labrad.types import Value

TIMEOUT = Value(5,'s')
BAUD    = 115200
STOP_BITS = 1
BYTESIZE= 8
RTS = 1

maxRate = 10

class AMI430Wrapper(DeviceWrapper):

    @inlineCallbacks
    def connect(self, server, port):
        """Connect to a device."""
        print('connecting to "%s" on port "%s"...' % (server.name, port), end=' ')
        self.server = server
        self.ctx = server.context()
        self.port = port
        p = self.packet()
        p.open(port)
        p.stopbits(STOP_BITS)
        p.bytesize(BYTESIZE)
        p.rts(bool(RTS))
        print('opened on port "%s"' %self.port)
        p.baudrate(BAUD)
        p.read()  # clear out the read buffer
        p.timeout(TIMEOUT)
        print(" CONNECTED ")
        yield p.send()
        
    def packet(self):
        """Create a packet in our private context."""
        return self.server.packet(context=self.ctx)

    def shutdown(self):
        """Disconnect from the serial port when we shut down."""
        return self.packet().close().send()

    @inlineCallbacks
    def write(self, code):
        """Write a data value to the heat switch."""
        yield self.packet().write(code).send()

    @inlineCallbacks
    def read(self):
        p=self.packet()
        p.read_line()
        ans=yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def query(self, code):
        """ Write, then read. """
        p = self.packet()
        p.write_line(code)
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)
        

class AMI430Server(DeviceServer):
    name = 'AMI_430'
    deviceName = 'AMI_430 Programmer'
    deviceWrapper = AMI430Wrapper

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
        # reg = self.client.registry
        # p = reg.packet()
        # p.cd(['', 'Servers', 'Heat Switch'], True)
        # p.get('Serial Links', '*(ss)', key='links')
        # ans = yield p.send()
        # self.serialLinks = ans['links']
        reg = self.reg
        yield reg.cd(['', 'Servers', 'ami_430', 'Links'], True)
        dirs, keys = yield reg.dir()
        p = reg.packet()
        print(" created packet")
        print("printing all the keys",keys)
        if keys:
            for k in keys:
                print("k=",k)
                p.get(k, key=k)
                
            ans = yield p.send()
            print("ans=",ans,ans[k])
            self.serialLinks = dict((k, ans[k]) for k in keys)
        else:
            self.serialLinks = dict()


        # yield reg.cd(['', 'Servers', 'ami_430', 'Max Rates'], True)
        # dirs, keys = yield reg.dir()
        # p = reg.packet()
        # for k in keys:
        #     p.get(k, key=k)
            
        # ans = yield p.send()
        # self.maxRates = dict((k, ans[k]) for k in keys)


    @inlineCallbacks
    def findDevices(self):
        """Find available devices from list stored in the registry."""
        devs = []
        # for name, port in self.serialLinks:
        # if name not in self.client.servers:
        # continue
        # server = self.client[name]
        # ports = yield server.list_serial_ports()
        # if port not in ports:
        # continue
        # devName = '%s - %s' % (name, port)
        # devs += [(devName, (server, port))]
        # returnValue(devs)
        for name, (serServer, port) in list(self.serialLinks.items()):
            if serServer not in self.client.servers:
                continue
            server = self.client[serServer]
            print(name)
            print(server)
            print(port)
            ports = yield server.list_serial_ports()
            print(ports)
            if port not in ports:
                continue
            devName = '%s - %s' % (serServer, port)
            devs += [(devName, (server, port))]

       # devs += [(0,(3,4))]
        returnValue(devs)

    @inlineCallbacks
    def get_max_rate(self,dev):
        pass

    
    @setting(100)
    def connect(self,c,server,port):
        dev=self.selectedDevice(c)
        yield dev.connect(server,port)

    @setting(101,returns='s')
    def id(self,c):
        dev=self.selectedDevice(c)
        yield dev.write('*IDN?\r')
        ans = yield dev.read()
        returnValue(ans)

    @setting(102,returns='s')
    def system_error(self,c):
        '''
        Queries the error buffer of the Model 430 Programmer. Up to 10 errors are
        stored in the error buffer. Errors are retrieved in first-in-first-out (FIFO)
        order. The error buffer is cleared by the *CLS (clear status) command or
        when the power is cycled. Errors are also cleared as they are read. See
        page 153 for a complete description of the error buffer and messages.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("*SYST:ERR?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(103,returns='s')
    def clear(self,c):
        '''
        Clears the Standard Event register and the error buffer.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("*CLS\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(104,voltage='v[]')
    def conf_volt_lim(self,c,voltage):
        '''
        Sets the ramping Voltage Limit in volts. The ramping Voltage Limit may
        not exceed the maximum output voltage of the power supply.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("CONF:VOLT:LIM %f\r"%voltage)

    @setting(105,returns='s')
    def get_volt_lim(self,c):
        '''
        Returns the ramping Voltage Limit in volts.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("VOLT:LIM?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(106,current='v[]')
    def conf_curr_targ(self,c,current):
        '''
        Sets the target current in amperes.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("CONF:CURR:TARG %f\r"%current)
        
    @setting(107,returns='s')
    def get_curr_targ(self,c):
        '''
        Returns the target current setting in amperes.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("CURR:TARG?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(108,units='v[]')
    def conf_field_units(self,c,units):
        '''
        Sets the preferred field units. Sending "0" selects kilogauss. A "1" selects
        tesla. "0" is the default value. The selected field units are applied to both
        the Model 430 Programmer display and the applicable remote commands.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("CONF:FIELD:UNITS %f\r"%units)

    @setting(109,returns='s')
    def get_field_units(self,c):
        '''
        Returns "0" for field values displayed/specified in terms of kilogauss, or "1"
        for tesla.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("FIELD:UNITS?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(110,field='v[]')
    def conf_field_targ(self,c,field):
        '''
        Sets the target field in units of kilogauss or tesla, per the selected field
        units. This command requires that a coil constant be defined, otherwise an
        error is generated.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("CONF:FIELD:TARG %f\r"%field)


    @setting(111,returns='s')
    def get_field_targ(self,c):
        '''
        Returns the target current setting in amperes.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("FIELD:TARG?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(112,nSegments='i')
    def conf_ramp_rate_seg(self,c,nSegments):
        '''
        Sets the number of ramp segments (see section 3.7.1 for details of the use
        of ramp segments).
        '''
        dev=self.selectedDevice(c)
        yield dev.write("CONF:RAMP:RATE:SEG %u\r"%nSegments)

    @setting(113,returns='s')
    def get_ramp_rate_seg(self,c):
        '''
        Returns the number of ramp segments.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("RAMP:RATE:SEG?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(114,units='i')
    def conf_ramp_rate_units(self,c,units):
        '''
        Sets the preferred ramp rate time units. Sending "0" selects seconds. A "1"
        selects minutes. "0" is the default value. The selected units are applied to
        both the Model 430 Programmer display and the appropriate remote
        commands.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("CONF:RAMP:RATE:UNITS %u\r"%units)

    @setting(115,returns='s')
    def get_ramp_rate_units(self,c):
        '''
        Returns "0" for ramp rates displayed/specified in terms of seconds, or "1"
        for minutes.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("RAMP:RATE:UNITS?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(116,segment='i', rate = 'v[]', upper_bound = 'v[]')
    def conf_ramp_rate_curr(self,c,segment,rate,upper_bound):
        '''
        Sets the ramp rate for the specified segment (values of 1 through the
        defined number of ramp segments are valid) in units of A/sec or A/min (per
        the selected ramp rate units), and defines the current upper bound for that
        segment in amperes (see section 3.7.1 for details of the use of ramp
        segments).
        '''
        dev=self.selectedDevice(c)
        rate = min(rate,maxRate)
        yield dev.write("CONF:RAMP:RATE:CURR %u,%f,%f\r"%(segment,rate,upper_bound))

    @setting(117,segment='i',returns='s')
    def get_ramp_rate_curr(self,c,segment):
        '''
        Returns the ramp rate setting for the specified segment (values of 1
        through the defined number of ramp segments are valid) in units of A/sec
        or A/min (per the selected ramp rate units) and the current upper bound 
        for that range in amperes. The two return values are separated by a
        comma.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("RAMP:RATE:CURR:%u?\r"%segment)
        ans = yield dev.read()
        returnValue(ans)

    @setting(118,segment='i', rate = 'v[]', upper_bound = 'v[]')
    def conf_ramp_rate_field(self,c,segment,rate,upper_bound):
        '''
        Sets the ramp rate for the specified segment (values of 1 through the
        defined number of ramp segments are valid) in units of kilogauss/second or
        minute, or tesla/second or minute (per the selected field units and ramp
        rate units), and defines the field upper bound for that segment in
        kilogauss or tesla (see section 3.7.1 for details of the use of ramp
        segments). This command requires that a coil constant be defined;
        otherwise, an error is generated.
        '''
        dev=self.selectedDevice(c)
        rate = min(rate,maxRate)
        yield dev.write("CONF:RAMP:RATE:FIELD %u,%f,%f\r"%(segment,rate,upper_bound))

    @setting(119,segment='i',returns='s')
    def get_ramp_rate_field(self,c,segment):
        '''
        Returns the ramp rate setting for the specified segment (values of 1
        through the defined number of ramp segments are valid) in units of
        kilogauss/second or minute, or tesla/second or minute (per the selected
        field units and ramp rate units) and the current upper bound for that
        range in kilogauss or tesla (per the selected field units). This command
        requires that a coil constant be defined; otherwise, an error is generated.
        The two return values are separated by a comma.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("RAMP:RATE:FIELD:%u?\r"%segment)
        ans = yield dev.read()
        returnValue(ans)

    @setting(120,returns='s')
    def get_volt_mag(self,c):
        '''
        Returns the magnet voltage in volts. Requires voltage taps to be installed
        across the magnet terminals.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("VOLT:MAG?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(121,returns='s')
    def get_volt_supp(self,c):
        '''
        Returns the power supply voltage commanded by the Model 430
        Programmer in volts.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("VOLT:SUPP?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(122,returns='s')
    def get_curr_mag(self,c):
        '''
        Returns the current flowing in the magnet in amperes, expressed as a
        number with four significant digits past the decimal point, such as 5.2320.
        If the magnet is in persistent mode, the command returns the current that
        was flowing in the magnet when persistent mode was entered.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("CURR:MAG?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(123,returns='s')
    def get_curr_supp(self,c):
        '''
        Returns the measured power supply current in amperes.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("CURR:SUPP?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(124,returns='s')
    def get_field_mag(self,c):
        '''
        Returns the calculated field in kilogauss or tesla, per the selected field
        units. This query requires that a coil constant be defined; otherwise, an
        error is generated. The field is calculated by multiplying the measured
        magnet current by the coil constant. If the magnet is in persistent mode,
        the command returns the field that was present when persistent mode was
        entered.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("FIELD:MAG?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(125,returns='s')
    def get_ind(self,c):
        '''
        Returns the measured magnet inductance in henries. Note that the
        magnet must be ramping when this command is executed. Refer to section
        3.10.2.5 on page 78.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("IND?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(126,units='i')
    def conf_rampDown_enab(self,c,units):
        '''
        Enables the external rampdown function. "1" enables while "0" disables.
        "0" is the default value.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("CONF:RAMPD:ENAB %u\r"%units)

    @setting(127,returns='s')
    def get_rampDown_enab(self,c):
        '''
        Queries whether the external rampdown function is enabled. Returns "1"
        for enabled while "0" for disabled. "0" is the default value.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("RAMPD:ENAB\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(128,nSegments='i')
    def conf_rampDown_rate_seg(self,c,nSegments):
        '''
        Sets the number of external rampdown segments.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("CONF:RAMPD:RATE:SEG %u\r"%nSegments)

    @setting(129,returns='s')
    def get_rampDown_rate_seg(self,c):
        '''
        Returns the number of external rampdown segments.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("RAMPD:RATE:SEG?\r")
        ans = yield dev.read()
        returnValue(ans)

    @setting(130,segment='i', rate = 'v[]', upper_bound = 'v[]')
    def conf_rampDown_rate_curr(self,c,segment,rate,upper_bound):
        '''
        Sets the external rampdown rate for the specified segment (values of 1
        through the defined number of rampdown segments are valid) in units of
        A/sec or A/min (per the selected rampdown rate units), and defines the
        current upper bound for that segment in amperes.
        '''
        dev=self.selectedDevice(c)
        rate = min(rate,maxRate)
        yield dev.write("CONF:RAMPD:RATE:CURR %u,%f,%f\r"%(segment,rate,upper_bound))

    @setting(131,segment='i',returns='s')
    def get_rampDown_rate_curr(self,c,segment):
        '''
        Returns the external rampdown rate setting for the specified segment
        (values of 1 through the defined number of rampdown segments are valid)
        in units of A/sec or A/min (per the selected rampdown rate units) and the
        current upper bound for that range in amperes. The two return values are
        separated by a comma.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("RAMPD:RATE:CURR:%u?\r"%segment)
        ans = yield dev.read()
        returnValue(ans)

    @setting(132,segment='i', rate = 'v[]', upper_bound = 'v[]')
    def conf_rampDown_rate_field(self,c,segment,rate,upper_bound):
        '''
        Sets the external rampdown rate for the specified segment (values of 1
        through the defined number of rampdown segments are valid) in units of
        A/sec or A/min (per the selected rampdown rate units), and defines the
        current upper bound for that segment in amperes.
        '''
        dev=self.selectedDevice(c)
        rate = min(rate,maxRate)
        yield dev.write("CONF:RAMPD:RATE:Field %u,%f,%f\r"%(segment,rate,upper_bound))

    @setting(133,segment='i',returns='s')
    def get_rampDown_rate_field(self,c,segment):
        '''
        Returns the external rampdown rate setting for the specified segment
        (values of 1 through the defined number of rampdown segments are valid)
        in units of kilogauss/second or minute, or tesla/second or minute (per the
        selected field units and rampdown rate units) and the current upper bound
        for that range in kilogauss or tesla (per the selected field units). This
        command requires that a coil constant has been defined; otherwise, an
        error is generated.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("RAMPD:RATE:CURR:%u?\r"%segment)
        ans = yield dev.read()
        returnValue(ans)

    @setting(134)
    def ramp(self,c):
        '''
        Places the Model 430 Programmer in automatic ramping mode. The Model
        430 will continue to ramp at the configured ramp rate(s) until the target
        field/current is achieved.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("RAMP\r")

    @setting(135)
    def pause(self,c):
        '''
        Pauses the Model 430 Programmer at the present operating field/current.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("PAUSE\r")

    @setting(136)
    def incr(self,c):
        '''
        Places the Model 430 Programmer in the MANUAL UP ramping mode.
        Ramping continues at the ramp rate until the Current Limit is achieved.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("INCR\r")

    @setting(137)
    def decr(self,c):
        '''
        Places the Model 430 Programmer in the MANUAL DOWN ramping
        mode. Ramping continues at the ramp rate until the Current Limit is
        achieved (or zero current is achieved for unipolar power supplies).
        '''
        dev=self.selectedDevice(c)
        yield dev.write("DECR\r")

    @setting(138)
    def zero(self,c):
        '''
        Places the Model 430 Programmer in ZEROING CURRENT mode.
        Ramping automatically initiates and continues at the ramp rate until the
        power supply output current is less than 0.1% of Imax, at which point the
        AT ZERO status becomes active.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("ZERO\r")

    @setting(139)
    def state(self,c, returns='i'):
        '''
        Returns an integer value corresponding to the ramping state:
        1 RAMPING to target field/Current    
        2 HOLDING at the target field/current    
        3 PAUSED     
        4 Ramping in MANUAL UP mode     
        5 Ramping in MANUAL DOWN mode     
        6 ZEROING CURRENT (in progress)     
        7 Quench detected     
        8 At ZERO current     
        9 Heating persistent switch     
        10 Cooling persistent switch     
        '''
        dev=self.selectedDevice(c)
        yield dev.write("STATE?\r")
        ans = yield dev.read()
        returnValue(int(ans))

    @setting(140,name='s')
    def conf_ipname(self,c,name):
        '''
        Sets the system name (also known as host name or computer name), the
        name by which the Model 430 Programmer is identified on a network.
        '''
        dev=self.selectedDevice(c)
        yield dev.write("CONF:IPNAME %s\r"%name)

    @setting(141,returns='s')
    def get_ipname(self,c):
        '''
        Returns the system name (also known as host name or computer name).
        '''
        dev=self.selectedDevice(c)
        yield dev.write("IPNAME?\r"%segment)
        ans = yield dev.read()
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

    
__server__ = AMI430Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)