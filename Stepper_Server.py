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
name = Stepper Motor Controllers
version = 1.0
description = ACBOX control

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

from labrad.server import setting
from labrad.devices import DeviceServer,DeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as units
from labrad.types import Value
from collections import deque
import time

TIMEOUT = Value(5,'s')
BAUD    = 9600
BYTESIZE = 8
STOPBITS = 1
PARITY = 0

class StepperWrapper(DeviceWrapper):

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
        p.read()  # clear out the read buffer
        p.timeout(TIMEOUT)
        #p.timeout(None)
        print(" CONNECTED ")
        yield p.send()

    def packet(self):
        """Create a packet in our private context"""
        return self.server.packet(context=self.ctx)

    def shutdown(self):
        """Disconnect from the serial port when we shut down"""
        return self.packet().close().send()

    @inlineCallbacks
    def write(self, code):
        """Write a data value to the device"""
        yield self.packet().write(code).send()

    @inlineCallbacks
    def read(self):
        """Read a response line from the device"""
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


class StepperServer(DeviceServer):
    name             = 'Stepper_Server'
    deviceName       = 'Evaporator Stepper Motor Controller'
    deviceWrapper    = StepperWrapper

    @inlineCallbacks
    def initServer(self):
        print('loading config info...', end=' ')
        self.reg = self.client.registry()
        yield self.loadConfigInfo()
        print('done.')
        print(self.serialLinks)
        yield DeviceServer.initServer(self)
        self.stack  = deque([])

    @inlineCallbacks
    def loadConfigInfo(self):
        reg = self.reg
        yield reg.cd(['', 'Servers', 'Evaporator Stepper', 'Links'], True)
        dirs, keys = yield reg.dir()
        p = reg.packet()
        print("Created packet")
        print("printing all the keys",keys)
        for k in keys:
            print("k=",k)
            p.get(k, key=k)
        ans = yield p.send()
        print("ans=",ans)
        self.serialLinks = dict((k, ans[k]) for k in keys)

    @inlineCallbacks
    def findDevices(self):
        devs = []
        for name, (serServer, port) in list(self.serialLinks.items()):
            if serServer not in self.client.servers:
                print(serServer)
                print(self.client.servers)
                continue
            server = self.client[serServer]
            ports = yield server.list_serial_ports()
            if port not in ports:
                continue
            devName = '%s - %s' % (serServer, port)
            devs += [(devName, (server, port))]
        returnValue(devs)

    @setting(505, stepper = 's', degrees = 's', direction = 's', returns='s')
    def rot(self,c,stepper, degrees, direction):
        """Rotates stepper motor by the number of degrees in the specified direction. The shutter blade
        stepper motor is motor 'A'. The cryostat stepper motor is motor 'B'. Use C to move clockwise and
        A to move anti-clockwise. Example command: A150C. This will turn stepper motor A 150 degrees
        clockwise."""
        stat = yield self.status(c)
        command = stepper+degrees+direction+"r"
        if stat.startswith('stationary') and len(self.stack) == 0:
            dev=self.selectedDevice(c)
            yield dev.write(command)
            ans = yield dev.read()
            returnValue(ans)
        else:
            self.stack.append(command)
            if len(self.stack) == 1:
                self.empty_stack(c)
            returnValue('Added to stack\r\n')

    @setting(506, returns='s')
    def iden(self,c):
        """Identifies the stepper controller device."""
        dev=self.selectedDevice(c)
        yield dev.write("ir")
        ans = yield dev.read()
        returnValue(ans)

    @setting(507,returns = 's')
    def status(self,c):
        """Returns the status (whether or not something is turning)."""
        dev=self.selectedDevice(c)
        yield dev.write("sr")
        ans = yield dev.read()
        returnValue(ans)

    @setting(508,returns = '')
    def empty_stack(self,c):
        """Works on emptying the stack. Should never need to be called manually."""
        dev=self.selectedDevice(c)
        while len(self.stack)>0:
            stat = yield self.status(c)
            if stat.startswith('stationary'):
                command = self.stack.popleft()
                yield dev.write(command)
                ans = yield dev.read()
                yield self.empty_stack(c)


__server__ = StepperServer()
if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
