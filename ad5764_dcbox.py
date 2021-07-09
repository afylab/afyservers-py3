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
name = ad5764_dcbox
version = 1.1.1
description = Arduino DC box server
[startup]
cmdline = %PYTHON% %FILE%
timeout = 20
[shutdown]
message = 987654321
timeout = 20    
### END NODE INFO
"""

from labrad.server import setting,Signal
from labrad.devices import DeviceServer,DeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as units
from labrad.types import Value

class serverInfo(object):
    def __init__(self):
        self.deviceName = 'Arduino DC Box' #'Server name in registry means this'
        self.serverName = "ad5764_dcbox"

    def getDeviceName(self,comPort):
        return "%s (%s)"%(self.serverName, comPort)

class arduinoDCBoxWrapper(DeviceWrapper):

    @inlineCallbacks
    def connect(self, server, port):
        """Connect to a device"""
        print(("Connecting to '%s' on port '%s'"%(server.name,port)))
        self.server = server
        self.ctx    = server.context()
        self.port   = port

        p = self.packet()
        p.open(port)
        print(("opened on port '%s'"%port))

        self.BAUDRATE   = 115200
        self.TIMEOUT    = Value(5,'s')

        p.baudrate(self.BAUDRATE) # set BAUDRATE
        p.read()                  # clear buffer
        p.timeout(self.TIMEOUT)   # sets timeout

        print("Connected.")
        yield p.send()

    def packet(self):
        """Create a packet in our private context"""
        return self.server.packet(context=self.ctx)

    def shutdown(self):
        """Disconnect from the serial port when we shut down"""
        return self.packet().close().send()

    @inlineCallbacks
    def set_voltage(self,port,value):
        if not (port in range(8)):
            returnValue("Error: invalid channel (was <%s>, should be integer from 0 to 7)"%(port,))
        if abs(value) > 10.0:
            returnValue("Error: invalid voltage (was <%s>, should be between -10 and 10)")
        yield self.packet().write("SET,%i,%f\r"%(port,value)).send()
        p=self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def get_voltage(self,port):
        if not (port in range(8)):
            returnValue("Error: invalid channel (was <%s>, should be integer from 0 to 7)"%(port,))
        yield self.packet().write("GET_DAC,%s\r\n"%port).send()
        p=self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)


class arduinoDCBoxServer(DeviceServer):
    info          = serverInfo()
    name          = info.serverName
    deviceName    = info.deviceName
    deviceWrapper = arduinoDCBoxWrapper
    
    # Signals (server prefix 701000)
    sPrefix=701000
    sigChannelVoltageChanged  = Signal(sPrefix + 10,'signal__channel_voltage_changed', '*s')

    validPorts = [0,1,2,3,4,5,6,7]

    @inlineCallbacks
    def initServer(self):
        print(("Server <%s> of type <%s>"%(self.name,self.deviceName)))
        self.reg = self.client.registry()
        yield self.loadConfigInfo()
        print((self.serialLinks))
        yield DeviceServer.initServer(self)

    @inlineCallbacks
    def loadConfigInfo(self):
        """Loads port/device info from the registry"""
        yield self.reg.cd(['','Servers',self.name,'Links'],True)
        dirs,keys = yield self.reg.dir()
        print(("Found devices: %s"%(keys,)))
        p   = self.reg.packet()
        for k in keys:p.get(k,key=k)
        ans = yield p.send()
        self.serialLinks = dict((k, ans[k]) for k in keys)

    @inlineCallbacks
    def findDevices(self):
        """Gets list of devices whose ports are active (available devices.)"""
        devs=[]
        for name,(serialServer,port) in list(self.serialLinks.items()):
            if serialServer not in self.client.servers:
                print(("Error: serial server (%s) not found. Device '%s' on port '%s' not active."%(serialServer,name,port)))
                continue
            ports = yield self.client[serialServer].list_serial_ports()
            if port not in ports:
                continue
            devs += [(self.info.getDeviceName(port),(self.client[serialServer],port))]
        returnValue(devs)

    @setting(100)
    def connect(self,c,server,port):
        dev=self.selectedDevice(c)
        yield dev.connect(server,port)

    @setting(200,port='i',voltage='v',returns='s')
    def set_voltage(self,c,port,voltage):
        """Sets the voltage at <port> to <voltage>"""
        if not (port in self.validPorts):
            returnValue("Error: invalid port. Port must be from 0 to 7.")
        if (voltage>10) or (voltage < -10):
            returnValue("Error: invalid voltage. It must be between -10 and 10.")

        dev = self.selectedDevice(c)
        ans = yield dev.set_voltage(port,voltage)
        val = ans.lower().partition(' to ')[2][:-1]
        yield self.sigChannelVoltageChanged([str(port),val])
        returnValue(ans)

    @setting(201,voltage='v',returns='*s')
    def set_all_voltages(self,c,voltage):
        """Sets all ports to <voltage>"""
        if (voltage > 10) or (voltage < -10):
            returnValue("Error: invalid voltage. It must be between -10 and 10.")

        dev = self.selectedDevice(c)
        ans = []
        for port in self.validPorts:
            resp = yield dev.set_voltage(port,voltage)
            val  = resp.lower().partition(' to ')[2][:-1]
            yield self.sigChannelVoltageChanged([str(port),val])
            ans.append(resp)
        returnValue(ans)

    @setting(210,port='i',returns='v')
    def get_voltage(self,c,port):
        if not (port in self.validPorts):
            returnValue("Error: invalid port. Port must be from 0 to 7.")
        dev = self.selectedDevice(c)
        ans = yield dev.get_voltage(port)
        returnValue(float(ans))

    @setting(211,returns='*v')
    def get_all(self,c):
        ans = []
        dev = self.selectedDevice(c)
        for port in self.validPorts:
            resp = yield dev.get_voltage(port)
            ans.append(float(resp))
        returnValue(ans)

    @setting(300)
    def send_voltage_signals(self,c):
        dev = self.selectedDevice(c)
        for port in self.validPorts:
            ans = yield dev.get_voltage(port)
            self.sigChannelVoltageChanged([str(port),ans])

__server__ = arduinoDCBoxServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
