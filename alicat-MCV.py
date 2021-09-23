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
name = Alicat MCV
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
# import labrad.units as units
from labrad.types import Value

TIMEOUT = Value(5,'s')
BAUD = 19200
BYTESIZE = 8
STOPBITS = 1
PARITY = 0

class alicatMCVWrapper(DeviceWrapper):
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
        p.readbuffer()  # clear out the read buffer
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
        p.readbuffer()
        ans=yield p.send()
        returnValue(ans.readbuffer)

    @inlineCallbacks
    def query(self, code):
        """ Write, then read. """
        p = self.packet()
        p.write(code)
        p.readbuffer()
        ans = yield p.send()
        returnValue(ans.readbuffer)

class AlicatMCVServer(DeviceServer):
    name = 'Alicat_MCV'
    deviceName = 'Alicat_MCV'
    deviceWrapper = alicatMCVWrapper

    @inlineCallbacks
    def initServer(self):
        self.pressure = 0
        self.temperature = 0
        self.vol_flow = 0
        self.mass_flow = 0
        self.gas = ''
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
        yield reg.cd(['', 'Servers', 'Alicat', 'Links'], True)
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
        returnValue(devs)

    @setting(100)
    def connect(self, c, server, port):
        dev=self.selectedDevice(c)
        yield dev.connect(server,port)

    @setting(101, returns='s')
    def poll(self,c):
        """Read data from the Alicat.
        Response: Sensor_Num Abs_Pressure Temperature Vol_Flow Mass_Flow Setpoint Gas

        Responses have + in front of them normally that needs to be stripped.
        """
        try:
            dev=self.selectedDevice(c)
            ans = yield dev.query("a\r")
            ans = ans.split()
            self.pressure = float(ans[1])
            self.temperature = float(ans[2])
            self.vol_flow = float(ans[3])
            self.mass_flow = float(ans[4])
            self.setpoint = float(ans[5])
            self.gas = str(ans[6])
        except:
            print("Could not read data")
        returnValue(str(ans))

    @setting(102, returns='?')
    def get_pressure(self,c):
        '''
        Poll the device and get the absolute pressure. Normally in PSIA
        '''
        yield self.poll(c)
        returnValue(self.pressure)

    @setting(103, returns='?')
    def get_temperature(self,c):
        '''
        Poll the device and get the temperature. Normally in C.
        '''
        yield self.poll(c)
        returnValue(self.temperature)

    @setting(104, returns='?')
    def get_vol_flow(self,c):
        '''
        Poll the device and get the volumetric flow. Normally in CCM.
        '''
        yield self.poll(c)
        returnValue(self.vol_flow)

    @setting(105, returns='?')
    def get_mass_flow(self,c):
        '''
        Poll the device and get the mass flow. Normally in SCCM.
        '''
        yield self.poll(c)
        returnValue(self.mass_flow)

    @setting(106, returns='?')
    def get_setpoint(self,c):
        '''
        Poll the device and get the setpoint. Normally in SCCM.
        '''
        yield self.poll(c)
        returnValue(self.setpoint)

    @setting(107, returns='?')
    def get_gas_setting(self,c):
        '''
        Poll the device and get the currently configured gas.
        '''
        yield self.poll(c)
        returnValue(self.gas)

    @setting(109, value='v', returns='?')
    def set_setpoint(self,c,value):
        '''
        Change the setpoint. Units usually in SCCM
        '''
        dev=self.selectedDevice(c)
        yield dev.write("as"+str(value)+"\r")

__server__ = AlicatMCVServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
