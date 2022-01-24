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
name = Arduino AC box server
version = 1.1
description = Arduino AC box server

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
        self.deviceName = 'Arduino AC Box'
        self.serverName = 'ad5764_acbox'

    def getDeviceName(self,comPort):
        return "%s (%s)"%(self.serverName,comPort)

class arduinoACBoxWrapper(DeviceWrapper):

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
    def do_init(self,clock_multiplier):
        yield self.packet().write("INIT,%i\r\n"%clock_multiplier).send()
        p=self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def do_reset(self):
        yield self.packet().write("MR\r\n").send()
        p=self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def identify(self):
        yield self.packet().write("*IDN?\r\n").send()
        p=self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def get_is_ready(self):
        yield self.packet().write("*RDY?\r\n").send()
        p=self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def update_boards(self):
        yield self.packet().write("UPD\r\n").send()
        p=self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def nop(self):
        yield self.packet().write("NOP\r\n").send()
        p=self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def set_voltage(self,channel,value):
        yield self.packet().write("SET,%s,%f\r\n"%(channel,value)).send()
        p=self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def set_phase(self,offset):
        offset = offset%360.0
        yield self.packet().write("PHS,1,%f\r\n"%offset).send()
        yield self.packet().write("PHS,2,0\r\n").send()
        p=self.packet();p.read_line();ans1 = yield p.send()
        p=self.packet();p.read_line();ans2 = yield p.send()
        returnValue(ans1.read_line)

    @inlineCallbacks
    def set_frequency(self,frequency):
        yield self.packet().write("FRQ,%f\r\n"%frequency).send()
        p=self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def get_voltage(self,channel):
        yield self.packet().write("GET,%s\r\n"%channel).send()
        p=self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def get_phase(self):
        yield self.packet().write("PHS?\r\n").send()
        p=self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

    @inlineCallbacks
    def get_frequency(self):
        yield self.packet().write("FRQ?\r\n").send()
        p=self.packet()
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)

class arduinoACBoxServer(DeviceServer):
    info          = serverInfo()
    name          = info.serverName
    deviceName    = info.deviceName
    deviceWrapper = arduinoACBoxWrapper

    # Signals (server prefix 700000)
    sPrefix = 700000
    sigChannelVoltageChanged   = Signal(sPrefix+0,'signal__channel_voltage_changed', "*s")
    sigChannelVoltageChangedX1 = Signal(sPrefix+1,'signal__channel_x1_voltage_changed',"s")
    sigChannelVoltageChangedX2 = Signal(sPrefix+2,'signal__channel_x2_voltage_changed',"s")
    sigChannelVoltageChangedY1 = Signal(sPrefix+3,'signal__channel_y1_voltage_changed',"s")
    sigChannelVoltageChangedY2 = Signal(sPrefix+4,'signal__channel_y2_voltage_changed',"s")

    sigFrequencyChanged = Signal(sPrefix+10,'signal__frequency_changed','s')
    sigPhaseChanged     = Signal(sPrefix+11,'signal__phase_changed'    ,'s')
    sigInitDone         = Signal(sPrefix+12,'signal__init_done'        ,'s')
    sigResetDone        = Signal(sPrefix+13,'signal__reset_done'       ,'s')

    sigChannels      = {'X1':sigChannelVoltageChangedX1,'Y1':sigChannelVoltageChangedY1,'X2':sigChannelVoltageChangedX2,'Y2':sigChannelVoltageChangedY2}
    channels         = ['X1','Y1','X2','Y2']
    clock_multiplier = 4

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

    @setting(200,clock_multiplier='i',returns='s')
    def initialize(self,c,clock_multiplier):
        if (clock_multiplier < 4) or (clock_multiplier > 20):
            returnValue("Error: clock multiplier must be between 4 and 20")
        dev=self.selectedDevice(c)
        ans = yield dev.do_init(clock_multiplier)
        self.clock_multiplier = clock_multiplier
        yield self.sigInitDone(ans)
        returnValue(ans)

    @setting(201,returns='s')
    def reset(self,c):
        dev = self.selectedDevice(c)
        ans = yield dev.do_reset()
        yield self.sigResetDone(ans)
        returnValue(ans)

    @setting(202,returns='s')
    def identify(self,c):
        dev = self.selectedDevice(c)
        ans = yield dev.identify()
        returnValue(ans)

    @setting(203,returns='b')
    def get_is_ready(self,c):
        dev = self.selectedDevice(c)
        ans = yield dev.get_is_ready()
        if ans == 'READY':returnValue(True)
        returnValue(False)

    @setting(204,returns='s')
    def update_boards(self,c):
        dev = self.selectedDevice(c)
        ans = yield dev.update_boards()
        returnValue(ans)

    @setting(300,channel='s',voltage='v',returns='s')
    def set_voltage(self,c,channel,voltage):
        if not (channel in self.channels):
            returnValue("Error: invalid channel. It must be one of X1,Y1,X2,Y2")
        if (voltage > 1.0) or (voltage < 0.0):
            returnValue("Error: invalid voltage. It must be between 0.0 and 1.0")
        dev  = self.selectedDevice(c)
        resp = yield dev.set_voltage(channel,voltage)
        upd  = yield dev.update_boards()
        ans  = resp.partition(' to ')[2]
        self.sigChannelVoltageChanged([channel,ans])
        self.sigChannels[channel](ans)
        returnValue(resp)

    @setting(301,voltage='v',returns='*s')
    def set_all(self,c,voltage):
        if (voltage > 1.0) or (voltage < 0.0):
            returnValue("Error: invalid voltage. It must be between 0.0 and 1.0")
        dev  = self.selectedDevice(c)
        anss = []
        for channel in self.channels:
            resp = yield dev.set_voltage(channel,voltage)
            ans  = resp.partition(' to ')[2]
            self.sigChannelVoltageChanged([channel,ans])
            self.sigChannels[channel](ans)
        upd = yield dev.update_boards()
        returnValue(anss)

    @setting(302,offset='v',returns='s')
    def set_phase(self,c,offset):
        offset %= 360.0
        dev  = self.selectedDevice(c)
        resp = yield dev.set_phase(offset)
        upd  = yield dev.update_boards()
        ans  = resp.partition(' to ')[2]
        self.sigPhaseChanged(ans)
        returnValue(resp)

    @setting(303,frequency='v',returns='s')
    def set_frequency(self,c,frequency):
        if frequency <= 0:
            returnValue("Error: frequency cannot be zero (or less.)")
        if frequency > (self.clock_multiplier * 20000000):
            returnValue("Error: frequency cannot exceed 20MHz * clock_multiplier, where clock_multiplier is the multiplier set with the initialize function. (currently %i)"%self.clock_multiplier)            
        dev  = self.selectedDevice(c)
        resp = yield dev.set_frequency(frequency)
        upd  = yield dev.update_boards()
        ans  = resp.partition(' to ')[2][:-3]
        self.sigFrequencyChanged(ans)
        returnValue(resp)

    @setting(400,channel='s',returns='v')
    def get_voltage(self,c,channel):
        if not (channel in self.channels):
            returnValue("Error: invalid channel. It must be one of X1,Y1,X2,Y2")
        dev = self.selectedDevice(c)
        ans = yield dev.get_voltage(channel)
        returnValue(float(ans))

    @setting(401,returns='v')
    def get_phase(self,c):
        dev = self.selectedDevice(c)
        ans = yield dev.get_phase()
        returnValue(float(ans))

    @setting(402,returns='v')
    def get_frequency(self,c):
        dev = self.selectedDevice(c)
        ans = yield dev.get_frequency()
        returnValue(float(ans))

    @setting(500)
    def send_signals(self,c):
        dev = self.selectedDevice(c)
        for channel in self.channels:
            ans = yield dev.get_voltage(channel)
            self.sigChannelVoltageChanged([channel,str(ans)])
            self.sigChannels[channel](str(ans))
        ans = yield dev.get_phase()
        self.sigPhaseChanged(str(ans))
        ans = yield dev.get_frequency()
        self.sigFrequencyChanged(str(ans))

__server__ = arduinoACBoxServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
