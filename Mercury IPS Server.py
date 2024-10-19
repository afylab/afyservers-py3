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
BAUD    = 115200
BYTESIZE = 8
STOPBITS = 1
PARITY = 0

class IPSWrapper(DeviceWrapper):

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
        returnValue(ans.read_line)    @setting(506, returns='s')
    def iden(self,c):
        """Identifies the stepper controller device."""
        dev=self.selectedDevice(c)
        yield dev.write("*IDN?\n")
        ans = yield dev.read()
        returnValue(ans)
        
    @inlineCallbacks
    def system(self,c):
        dev=self.selectedDevice(c)
        print("Writting X")
        yield dev.write("READ:SYS:CAT\n")
        ans = yield dev.read()
        returnValue(ans)
        
    @inlineCallbacks
    def get_current(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:CURR\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
        
    @inlineCallbacks
    def get_volts(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:VOLT\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)

    @inlineCallbacks
    def get_persistent_current(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:PCUR\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
    
    @setting(511, returns='s')
    def get_field(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:FLD\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
    
    @inlineCallbacks
    def get_persistent_field(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:PFLD\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
        
    
    @inlineCallbacks
    def get_target_current(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:CSET\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
    @inlineCallbacks
    def get_target_field(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:FSET\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
       
    @inlineCallbacks
    def get_current_ramp_rate(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:RCST\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans) 
    
    @inlineCallbacks
    def get_field_ramp_rate(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:RFST\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
    
    @inlineCallbacks
    def get_switch_heater_status(self, c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:SWHT\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        returnValue(ans)
        
    @inlineCallbacks
    def switchHeaterON(self, c):
        dev=self.selectedDevice(c)
        yield dev.write("SET:DEV:GRPZ:PSU:SIG:SWHT:ON\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
        
    @inlineCallbacks  
    def switchHeaterOFF(self, c):
        dev=self.selectedDevice(c)
        yield dev.write("SET:DEV:GRPZ:PSU:SIG:SWHT:OFF\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
        
    @inlineCallbacks
    def set_target_field(self, c, target):
        dev=self.selectedDevice(c)
        yield dev.write("SET:DEV:GRPZ:PSU:SIG:FSET:"+str(target)+"\n")
        ans = yield dev.read()
        returnValue(ans)
    
    @inlineCallbacks
    def set_field_ramp_rate(self, c, target):
        dev=self.selectedDevice(c)
        yield dev.write("SET:DEV:GRPZ:PSU:SIG:RFST:"+str(target)+"\n")
        ans = yield dev.read()
        returnValue(ans)
    
    @inlineCallbacks
    def set_current(self, c, target):
        dev=self.selectedDevice(c)
        yield dev.write("SET:DEV:GRPZ:PSU:SIG:CSET:"+str(target)+"\n")
        ans = yield dev.read()
        returnValue(ans)


class IPSServer(DeviceServer):
    name             = 'Mercury IPS Server'
    deviceName       = 'Mercury IPS Magnet Control'
    deviceWrapper    = IPSWrapper

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
        yield reg.cd(['', 'Servers', 'Mercury IPS Server', 'Links'], True)
        dirs, keys = yield reg.dir()
        p = reg.packet()
        print("Created packet")
        print("printing all the keys",keys)
        for k in keys:
            print("k=",k)
            p.get(k, key=k)
        ans = yield p.send()
        #print("ans=",ans)
        self.serialLinks = dict((k, ans[k]) for k in keys)

    @inlineCallbacks
    def findDevices(self):
        devs = []
        for name, (serServer, port) in list(self.serialLinks.items()):
            if serServer not in self.client.servers:
                print(serServer)
                #print(self.client.servers)
                continue
            server = self.client[serServer]
            ports = yield server.list_serial_ports()
            if port not in ports:
                continue
            devName = '%s - %s' % (serServer, port)
            devs += [(devName, (server, port))]
        returnValue(devs)

    @setting(506, returns='s')
    def iden(self,c):
        """Identifies the stepper controller device."""
        dev=self.selectedDevice(c)
        yield dev.write("*IDN?\n")
        ans = yield dev.read()
        returnValue(ans)
        
    @setting(507, returns='s')
    def system(self,c):
        dev=self.selectedDevice(c)
        print("Writting X")
        yield dev.write("READ:SYS:CAT\n")
        ans = yield dev.read()
        returnValue(ans)
        
    @setting(508, returns='s')
    def get_current(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:CURR\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
        
    @setting(509, returns='s')
    def get_volts(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:VOLT\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)

    @setting(510, returns='s')
    def get_persistent_current(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:PCUR\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
    
    @setting(511, returns='s')
    def get_field(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:FLD\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
    
    @setting(512, returns='s')
    def get_persistent_field(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:PFLD\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
        
    
    @setting(513, returns='s')
    def get_target_current(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:CSET\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
       
    @setting(514, returns='s')
    def get_target_field(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:FSET\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
       
    @setting(515, returns='s')
    def get_current_ramp_rate(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:RCST\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans) 
    
    @setting(516, returns='s')
    def get_field_ramp_rate(self,c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:RFST\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
    
    @setting(517, returns='s')
    def get_switch_heater_status(self, c):
        dev=self.selectedDevice(c)
        yield dev.write("READ:DEV:GRPZ:PSU:SIG:SWHT\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        returnValue(ans)
        
    @setting(518, returns='s')
    def switchHeaterON(self, c):
        dev=self.selectedDevice(c)
        yield dev.write("SET:DEV:GRPZ:PSU:SIG:SWHT:ON\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
        
    @setting(519, returns='s')    
    def switchHeaterOFF(self, c):
        dev=self.selectedDevice(c)
        yield dev.write("SET:DEV:GRPZ:PSU:SIG:SWHT:OFF\n")
        ans = yield dev.read()
        ANS = ans.split(':')
        ans = ANS[-1]
        ans = ans[:-1]
        returnValue(ans)
        
    @setting(520, target ='v', returns='s') 
    def set_target_field(self, c, target):
        dev=self.selectedDevice(c)
        yield dev.write("SET:DEV:GRPZ:PSU:SIG:FSET:"+str(target)+"\n")
        ans = yield dev.read()
        returnValue(ans)
    
    @setting(521, target ='v', returns='s') 
    def set_field_ramp_rate(self, c, target):
        dev=self.selectedDevice(c)
        yield dev.write("SET:DEV:GRPZ:PSU:SIG:RFST:"+str(target)+"\n")
        ans = yield dev.read()
        returnValue(ans)
    
    @setting(522, target ='v', returns='s') 
    def set_current(self, c, target):
        dev=self.selectedDevice(c)
        yield dev.write("SET:DEV:GRPZ:PSU:SIG:CSET:"+str(target)+"\n")
        ans = yield dev.read()
        returnValue(ans)
    
    @setting(523, returns='s') 
    def start_ramping(self, c):
        dev=self.selectedDevice(c)
        yield dev.write("SET:DEV:GRPZ:PSU:ACTN:RTOS"+"\n")
        ans = yield dev.read()
        returnValue(ans)
    
    @setting(524, returns='s') 
    def stop_ramping(self, c):
        dev=self.selectedDevice(c)
        yield dev.write("SET:DEV:GRPZ:PSU:ACTN:HOLD"+"\n")
        ans = yield dev.read()
        returnValue(ans)
    
    
    
    
__server__ = IPSServer()
if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
