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
name = Lake Shore 336 temperature controller
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

import platform
global serial_server_name
serial_server_name = platform.node() + '_serial_server'

from labrad.server import setting
from labrad.devices import DeviceServer,DeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as units
from labrad.types import Value

TIMEOUT = Value(5,'s')
BAUD    = 57600
PARITY = 'O'
STOP_BITS = 1
BYTESIZE= 7

class LakeShore336Wrapper(DeviceWrapper):

    @inlineCallbacks
    def connect(self, server, port):
        """Connect to a device."""
        print('connecting to "%s" on port "%s"...' % (server.name, port), end=' ')
        self.server = server
        self.ctx = server.context()
        self.port = port
        p = self.packet()
        p.open(port)
        print('opened on port "%s"' %self.port)
        p.baudrate(BAUD)
        p.parity(PARITY)
        p.stopbits(STOP_BITS)
        p.bytesize(BYTESIZE)
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
        """Write a data value to the temperature controller."""
        yield self.packet().write(code).send()

    @inlineCallbacks
    def range_set(self, output, range):
        yield self.write("RANGE%i,%i" %(output, range))

    @inlineCallbacks
    def range_read(self, output):
        ans = yield self.query("RANGE?%i" %output)
        returnValue(ans)

    @inlineCallbacks
    def setpoint(self, output, setp):
        yield self.write('SETP%i,%f'%(output, setp))

    @inlineCallbacks
    def setpoint_read(self, output):
        ans = yield self.query("SETP?%i" %output)
        returnValue(ans)

    @inlineCallbacks
    def PID_set(self, output, prop, integ, deriv):
        yield self.write("PID%i,%f,%f,%f" %(output, prop, integ, deriv))

    @inlineCallbacks
    def PID_read(self, output):
        ans = yield self.query("PID?%i" %output)
        returnValue(ans)

    @inlineCallbacks
    def out_mode_set(self, output, mode, input, powerup_enable):
        yield self.write("OUTMODE%i,%i,%i,%i" %(output, mode, input, powerup_enable))

    @inlineCallbacks
    def out_mode_read(self, output):
        ans = yield self.query("OUTMODE?%i" %output)
        returnValue(ans)

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


class LakeShore336Server(DeviceServer):
    name = 'lakeshore_336'
    deviceName = 'Lake Shore 336 temperature controller'
    deviceWrapper = LakeShore336Wrapper

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
        yield reg.cd(['', 'Servers', 'LakeShore336', 'Links'], True)
        dirs, keys = yield reg.dir()
        print(dirs) # DEBUG
        print(keys) # DEBUG
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

    @setting(100)
    def connect(self,c,server,port):
        dev=self.selectedDevice(c)
        yield dev.connect(server,port)

    @setting(101,returns='s')
    def ID(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("*IDN?\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(102, channel='s',returns='s')
    def read_temp(self,c,channel):
        dev=self.selectedDevice(c)
        yield dev.write("KRDG? %s\n"%channel)
        ans = yield dev.read()
        returnValue(ans)

    @setting(103, channel='i',p='v')
    def set_p(self,c,channel,p):
        dev=self.selectedDevice(c)
        yield dev.write("SETP %s,%s\n"%(channel,p))

    @setting(104, channel='i',returns='s')
    def read_p(self,c,channel):
        dev=self.selectedDevice(c)
        yield dev.write("SETP? %s\n"%channel)
        ans = yield dev.read()
        returnValue(ans)

    @setting(105, channel='i',returns='s')
    def read_heater_ouput(self,c,channel):
        dev=self.selectedDevice(c)
        yield dev.write("HTR? %s\n"%channel)
        ans = yield dev.read()
        returnValue(ans)

    @setting(106, channel='i', range='i')
    def set_heater_range(self,c,channel,range):
        dev=self.selectedDevice(c)
        yield dev.write("RANGE %s,%s\n"%(channel,range))

    @setting(107, channel='i',returns='s')
    def read_heater_range(self,c,channel):
        dev=self.selectedDevice(c)
        yield dev.write("RANGE? %s\n"%channel)
        ans = yield dev.read()
        returnValue(ans)

    @setting(108, channel='i', resistance='i',max_current='i', max_user_current='v',output_display='i')
    def set_heater(self,c,channel,resistance,max_current,max_user_current,output_display):
        dev=self.selectedDevice(c)
        yield dev.write("HTRSET %s,%s,%s,%s,%s\n"%(channel,resistance,max_current,max_user_current,output_display))

    @setting(109, channel='i',returns='s')
    def read_heater_setup(self,c,channel):
        dev=self.selectedDevice(c)
        yield dev.write("HTRSET? %s\n"%channel)
        ans = yield dev.read()
        returnValue(ans)

    @setting(111, output = 'i', prop = 'v[]', integ = 'v[]', deriv = 'v[]')
    def pid_set(self, c, output, prop, integ, deriv):
        """
        Set the PID parameters for a specified output. 0.1 < P < 1000, 0.1 < I < 1000, 0 < D < 200.
        """
        dev=self.selectedDevice(c)
        yield dev.PID_set(output, prop, integ, deriv)

    @setting(112, output = 'i', returns='s')
    def pid_read(self, c, output):
        """
        Reads the PID parameters for a specified output.
        """
        dev=self.selectedDevice(c)
        ans = yield dev.PID_read(output)
        returnValue(ans)

    @setting(117, output = 'i', returns='i')
    def range_read(self, c, output):
        """
        Reads the range for a specified output. Refer to the documentation for range_set for a description of the return value.
        """
        dev=self.selectedDevice(c)
        ans = yield dev.range_read(output)
        returnValue(int(ans))

    @setting(118, output = 'i', setp = 'v[]')
    def setpoint(self, c, output, setp):
        """
        Sets the temperature setpoint for a specified output.
        """
        dev=self.selectedDevice(c)
        yield dev.setpoint(output, setp)

    @setting(119, output = 'i', returns='s')
    def setpoint_read(self, c, output):
        """
        Reads the temperature setpoint for a specified output.
        """
        dev=self.selectedDevice(c)
        ans = yield dev.setpoint_read(output)
        returnValue(ans)

    @setting(120, output = 'i', mode = 'i', input = 'i', powerup_enable = 'i')
    def out_mode_set(self, c, output, mode, input, powerup_enable):
        """
        Sets the output mode for a specified channel. User inputs which output to configure, the desired control mode (0 = Off,
        1 = PID Control, 2 = Zone, 3 = Open Loop, 4 = Monitor Out, 5 = Warmup Supply), which input to use for the control (1 = A,
        2 = B, 3 = C, 4 = D), and whether the output stays on or shuts off after a power cycle (0 = shuts off, 1 = remians on).
        """
        dev=self.selectedDevice(c)
        yield dev.out_mode_set(output, mode, input, powerup_enable)

    @setting(121, output = 'i', returns='s')
    def out_mode_read(self, c, output):
        """
        Reads the output mode settings for a specified output (the meaning of the returned list is documented in out_mode_set).
        """
        dev=self.selectedDevice(c)
        ans = yield dev.out_mode_read(output)
        returnValue(ans)

    @setting(122, output = 'i', range = 'i')
    def range_set(self, c, output, range):
        """
        Sets the range for a specified output. Outputs 1 and 2 have 5 available ranges, and outputs 3 and 4 are either 0 = off or 1 = on.
        """
        dev=self.selectedDevice(c)
        yield dev.range_set(output, range)

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


__server__ = LakeShore336Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
