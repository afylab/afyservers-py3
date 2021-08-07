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
name = Lake Shore 350 temperature controller
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

class LakeShore350Wrapper(DeviceWrapper):

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
        

class LakeShore350Server(DeviceServer):
    name = 'lakeshore_350'
    deviceName = 'Lake Shore 350 temperature controller'
    deviceWrapper = LakeShore350Wrapper 

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
        yield reg.cd(['', 'Servers', 'LakeShore350', 'Links'], True)
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

    
__server__ = LakeShore350Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)