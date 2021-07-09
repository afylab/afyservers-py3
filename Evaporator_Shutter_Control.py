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

class EvaporatorShutterWrapper(DeviceWrapper):

    @inlineCallbacks
    def connect(self, server, port='COM8'):
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


class EvaporatorShutter(DeviceServer):
    name             = 'evaporator_shutter_server'
    deviceName       = 'Evaporator Shutter Controller'
    deviceWrapper    = EvaporatorShutterWrapper

    @inlineCallbacks
    def initServer(self):
        '''
        Assumes the shutter is closed when the server starts, if this is not true
        a recalibration will be needed.
        '''
        print('loading config info...', end=' ')
        self.reg = self.client.registry()
        yield self.loadConfigInfo()
        print('done.')
        print(self.serialLinks)
        yield DeviceServer.initServer(self)
        self.stack  = deque([])
        self.evap_open = False
        self.effusion_open = False

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

    @setting(505, returns='s')
    def iden(self,c):
        """Identifies the stepper controller device."""
        dev=self.selectedDevice(c)
        yield dev.write("ir")
        ans = yield dev.read()
        returnValue(ans)

    @setting(506,returns = 's')
    def status(self,c):
        """Returns the status (whether or not something is turning)."""
        dev=self.selectedDevice(c)
        yield dev.write("sr")
        ans = yield dev.read()
        returnValue(ans)

    @setting(507,returns = '')
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

    @setting(508, degrees = 's', direction = 's', returns='s')
    def rot(self,c, degrees, direction):
        """
        From the Generic Stepper Server, do not call unless resetting the open/close
        state, because calling this will cause the server to lose track of the position.

        Rotates stepper motor by the number of degrees in the specified direction.
        Use C to move clockwise and A to move anti-clockwise.
        Example command: A150C. This will turn stepper motor A 150 degrees clockwise.
        """
        stat = yield self.status(c)
        command = "A"+degrees+direction+"r" # The first A selects the shutter blads stepper motor
        if stat.startswith('stationary') and len(self.stack) == 0:
            dev=self.selectedDevice(c)
            yield dev.write(command)
            ans = yield dev.read()
            returnValue(ans)
        else:
            self.stack.append(command)
            if len(self.stack) == 1:
                self.empty_stack(c)
            returnValue('Rotated ' + str(degrees))
    #

    @setting(509,returns = 's')
    def open_shutter(self,c):
        """Opens the shutter, does nothing if the shutter is already open"""
        if not self.evap_open:
            ret = yield self.rot(c, "35", "A")
            self.evap_open = True
            return ret
        return "No change"
    #

    @setting(510,returns = 's')
    def close_shutter(self,c):
        """Closes the shutter, does nothing if the shutter is already closed"""
        if self.evap_open:
            ret = yield self.rot(c, "35", "C")
            self.evap_open = False
            return ret
        return "No change"
    #

    @setting(511,returns = '')
    def open_effusion_shutter(self,c):
        """Opens the shutter, does nothing if the shutter is already open"""
        if len(self.stack) == 0:
            dev = self.selectedDevice(c)
            yield dev.write('eor')
            ans = yield dev.read()
            self.effusion_open = True
            print('Effusion shutter open')
        else:
            self.stack.append('eor')
            if len(self.stack) == 1:
                self.empty_stack(c)
            self.effusion_open = True
            print('Effusion shutter open')

    @setting(512,returns = '')
    def close_effusion_shutter(self,c):
        """Closes the shutter, does nothing if the shutter is already closed"""
        if len(self.stack) == 0:
            dev = self.selectedDevice(c)
            yield dev.write('ecr')
            ans = yield dev.read()
            self.effusion_open = False
            print('Effusion shutter closed')
        else:
            self.stack.append('ecr')
            if len(self.stack) == 1:
                self.empty_stack(c)
            self.effusion_open = False
            print('Effusion shutter closed')
    #

    @setting(513,returns = 's')
    def manual_reset_close(self,c):
        """Closes the shutter, does nothing if the shutter is already closed"""
        self.open = False
        return "Manually set state to close"
    #
    @setting(514,returns = 's')
    def returnstate(self,c):
        return self.open

__server__ = EvaporatorShutter()
if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
