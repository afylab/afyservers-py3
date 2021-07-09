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
name = Valve / Relay Controller
version = 1.0
description = Controller for Evaporator Valves and Relays

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
serial_server_name = (platform.node() + '_serial_server').replace('-', '_').lower()

from labrad.server import setting
from labrad.devices import DeviceServer, DeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as units
from labrad.types import Value
import time

from traceback import format_exc

TIMEOUT = Value(5, 's')
BAUD = 9600
BYTESIZE = 8
STOPBITS = 1
PARITY = 0

class ValveRelayWrapper(DeviceWrapper):

    @inlineCallbacks
    def connect(self, server, port):
        """Connect to a device."""
        print('connecting to "%s" on port "%s"...' % (server.name, port), end=' ')
        self.server = server
        self.ctx = server.context()
        self.port = port
        p = self.packet()
        # p.open(port)
        # Testing no pulse serial connect
        p.open(port, True)
        p.baudrate(BAUD)
        p.bytesize(BYTESIZE)
        p.stopbits(STOPBITS)
        p.setParity = PARITY
        p.read()  # clear out the read buffer
        p.timeout(TIMEOUT)
        # p.timeout(None)
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
        p = self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def query(self, code):
        """ Write, then read. """
        p = self.packet()
        p.write_line(code)
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)


class ValveRelayServer(DeviceServer):
    name = 'valve_relay_server'
    deviceName = 'Valve and Relay Controller'
    deviceWrapper = ValveRelayWrapper
    def __init__(self):
        super().__init__()
        self.state = dict()
        self.state['turbo pump'] = False
        self.state['scroll pump'] = False
        self.state['gate valve'] = False
        self.state['chamber valve'] = False
        self.state['turbo valve'] = False

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
        reg = self.reg
        yield reg.cd(['', 'Servers', 'Evaporator Valves/Relays', 'Links'], True)
        dirs, keys = yield reg.dir()
        p = reg.packet()
        print("Created packet")
        print("printing all the keys", keys)
        for k in keys:
            print("k=", k)
            p.get(k, key=k)
        ans = yield p.send()
        print("ans=", ans)
        self.serialLinks = dict((k, ans[k]) for k in keys)

    @inlineCallbacks
    def findDevices(self):
        try:
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
            return devs
        except:
            print(format_exc())

    @setting(405, returns='s')
    def turbo_valve_open(self, c):
        """Opens turbo valve."""
        dev = self.selectedDevice(c)
        yield dev.write("otr")
        ans = yield dev.read()
        self.state['turbo valve'] = True
        return ans

    @setting(406, returns='s')
    def turbo_valve_close(self, c):
        """Closess turbo valve."""
        dev = self.selectedDevice(c)
        yield dev.write("ctr")
        ans = yield dev.read()
        self.state['turbo valve'] = False
        return ans

    @setting(407, returns='s')
    def chamber_valve_open(self, c):
        """Opens chamber valve."""
        dev = self.selectedDevice(c)
        yield dev.write("ocr")
        ans = yield dev.read()
        self.state['chamber valve'] = True
        return ans

    @setting(408, returns='s')
    def chamber_valve_close(self, c):
        """Closes chamber valve."""
        dev = self.selectedDevice(c)
        yield dev.write("ccr")
        ans = yield dev.read()
        self.state['chamber valve'] = False
        return ans

    @setting(409, returns='s')
    def gate_open(self, c):
        """Opens Gate valve."""
        dev = self.selectedDevice(c)
        yield dev.write("ogr")
        ans = yield dev.read()
        self.state['gate valve'] = True
        return ans

    @setting(410, returns='s')
    def gate_close(self, c):
        """Closes Gate valve."""
        dev = self.selectedDevice(c)
        yield dev.write("cgr")
        ans = yield dev.read()
        self.state['gate valve'] = False
        return ans

    # @setting(411,returns='s')
    # def valve_four_open(self,c):
    #     """Opens valve 4."""
    #     dev=self.selectedDevice(c)
    #     yield dev.write("o4r")
    #     ans = yield dev.read()
    #     return ans
    #
    # @setting(412,returns='s')
    # def valve_four_close(self,c):
    #     """Closes valve 4."""
    #     dev=self.selectedDevice(c)
    #     yield dev.write("c4r")
    #     ans = yield dev.read()
    #     return ans
    #
    # @setting(413,returns='s')
    # def valve_five_open(self,c):
    #     """Opens valve 5."""
    #     dev=self.selectedDevice(c)
    #     yield dev.write("o5r")
    #     ans = yield dev.read()
    #     return ans
    #
    # @setting(414,returns='s')
    # def valve_five_close(self,c):
    #     """Closes valve 5."""
    #     dev=self.selectedDevice(c)
    #     yield dev.write("c5r")
    #     ans = yield dev.read()
    #     return ans
    #
    # @setting(415,returns='s')
    # def valve_six_open(self,c):
    #     """Opens valve 6."""
    #     dev=self.selectedDevice(c)
    #     yield dev.write("o6r")
    #     ans = yield dev.read()
    #     return ans
    #
    # @setting(416,returns='s')
    # def valve_six_close(self,c):
    #     """Closes valve 6."""
    #     dev=self.selectedDevice(c)
    #     yield dev.write("c6r")
    #     ans = yield dev.read()
    #     return ans

    @setting(417, returns='s')
    def iden(self, c):
        """Identifies the valve controller."""
        dev = self.selectedDevice(c)
        yield dev.write("ir")
        ans = yield dev.read()
        return ans

    @setting(418, returns='s')
    def scroll_on(self, c):
        """Starts the scroll pump."""
        dev = self.selectedDevice(c)
        yield dev.write("spr")
        ans = yield dev.read()
        self.state['scroll pump'] = True
        return ans

    @setting(419, returns='s')
    def scroll_off(self, c):
        """Stops the scroll pump."""
        dev = self.selectedDevice(c)
        yield dev.write("ssr")
        ans = yield dev.read()
        self.state['scroll pump'] = False
        return ans

    @setting(420, returns='s')
    def turbo_on(self, c):
        """Starts the turbo pump."""
        dev = self.selectedDevice(c)
        yield dev.write("tpr")
        ans = yield dev.read()
        self.state['turbo pump'] = True
        return ans

    @setting(421, returns='s')
    def turbo_off(self, c):
        """Stops the turbo pump."""
        dev = self.selectedDevice(c)
        yield dev.write("tsr")
        ans = yield dev.read()
        self.state['turbo pump'] = False
        return ans

    @setting(422, name='s', returns='b')
    def returnstate(self, c, name):
        return self.state[name]
#


__server__ = ValveRelayServer()
if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
