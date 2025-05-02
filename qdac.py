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
name = qdac
version = 1.0
description = QDevil 24-channel voltage source with 25-bit resolution
[startup]
cmdline = %PYTHON% %FILE%
timeout = 20
[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad.server import setting, Signal
from labrad.devices import DeviceServer,DeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor, defer
from labrad.types import Value
import time
import numpy as np

TIMEOUT = Value(5,'s')
BAUD = 921600
PARITY = 'N'
STOP_BITS = 1
BYTESIZE = 8

class qdacWrapper(DeviceWrapper):

    @inlineCallbacks
    def connect(self, server, port):
        """Connect to a device."""
        print('connecting to "%s" on port "%s"...' % (server.name, port), end=' ')
        self.server = server
        self.ctx = server.context()
        self.port = port
        self.ramping = False
        p = self.packet()
        p.open(port)
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

class qdacServer(DeviceServer):
    name = 'qdac'
    deviceName = 'QDevil QDAC-II'
    deviceWrapper = qdacWrapper

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
        reg = self.reg
        yield reg.cd(['', 'Servers', 'qdac', 'Links'], True)
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
            ports = yield server.list_serial_ports()
            if port not in ports:
                continue
            devName = '%s (%s)' % (name, port)
            devs += [(devName, (server, port))]
        returnValue(devs)

    @setting(100)
    def connect(self,c,server,port):
        dev=self.selectedDevice(c)
        yield dev.connect(server,port)
        
    @setting(101,returns='s')
    def id(self,c):
        dev=self.selectedDevice(c)
        ans=yield dev.query("*IDN?\n")
        returnValue(ans)
        
    @setting(102)
    def get_error(self,c):
        dev=self.selectedDevice(c)
        ans=yield dev.query("SYST:ERR?\n")
        returnValue(ans)
        
    @setting(103)
    def get_all_errors(self,c):
        dev=self.selectedDevice(c)
        ans=yield dev.query("SYST:ERR:ALL?\n")
        returnValue(ans)
    
    @setting(104)
    def abort():
        """
        Immediately halts all running voltage sweeps and waveforms
        """
        dev=self.selectedDevice(c)
        ans=yield dev.write("*ABOR\n")
        returnValue(ans)
        
    @setting(105,port='i',voltage='v')
    def set_voltage(self,c,port,voltage):
        """
        Sets a fixed voltage to a channel and returns the channel and the voltage it set.
        """
        dev=self.selectedDevice(c)
        dev.write("SOUR%i:DC:VOLT:MODE FIX\n"%(port))
        ans=yield dev.write("SOUR%i:DC:VOLT %f\n"%(port,voltage))
        returnValue(ans)
    
    @setting(106,port='i')
    def get_voltage(self,c,port):
        """
        Returns the present output voltage of a given channel and returns the channel and the voltage it set.
        """
        dev=self.selectedDevice(c)
        ans=yield dev.query("SOUR%i:DC:VOLT?\n"%port)
        returnValue(ans)
     
    @setting(107,port='i',start='v',end='v',points='i',dwell='v', trig='i', ttlwidth='v')
    def ramp1_ttl(self,c,port,start,end,points,dwell,trig,ttlwidth=0.0001):
        """
        Sweeps a single channel from start to end voltage, at the given dwell time in s
        The TTL output is triggered on every step of the ramp. Default pulse width: 100usec
        """
        if (ttlwidth >= dwell):
            print("TTL pulse width too long - increase dwell time or decrease TTL width")
            return "TTL pulse width too long - increase dwell time or decrease TTL width"
        dev=self.selectedDevice(c)
        dev.write("SOUR%i:DC:VOLT:MODE SWE\n"%(port))
        dev.write("SOUR%i:SWE:STAR %f\n"%(port,start))
        dev.write("SOUR%i:SWE:STOP %f\n"%(port,end))
        dev.write("SOUR%i:SWE:COUN 1\n"%(port))
        dev.write("SOUR%i:SWE:POIN %i\n"%(port,points))
        dev.write("SOUR%i:SWE:DWEL %f\n"%(port,dwell))
        dev.write("SOUR%i:DC:MARK:SSTART:TNUM 1\n"%(port)) #tie internal trigger number 1 to every step
        dev.write("OUTP:TRIG%i:SOUR INT1\n"%(trig))
        dev.write("OUTP:TRIG%i:WIDTH %f\n"%(trig,ttlwidth))
        ans=yield dev.write("SOUR%i:DC:INIT\n"%(port))
        returnValue(ans)
    
    @setting(115,ports='*i',start_vs='*v',end_vs='*v',points='i',dwell='v', trig='i', ttlwidth='v')
    def ramp_ttl(self,c,ports,start_vs,end_vs,points,dwell,trig,ttlwidth=0.0001):
        """
        Sweeps multiple channels from start to end voltages, at the given dwell time in s
        The specified TTL output is triggered on every step of the ramp. Default pulse width: 100usec
        """
        if (ttlwidth >= dwell):
            print("TTL pulse width too long - increase dwell time or decrease TTL width")
            return "TTL pulse width too long - increase dwell time or decrease TTL width"
        dev=self.selectedDevice(c)
        portString = '(@'+','.join([str(e) for e in ports])+')'
        dev.write("SOUR:DC:VOLT:MODE SWE, "+portString+"\n")
        dev.write("SOUR:SWE:COUN 1, "+portString+"\n")
        dev.write(("SOUR:SWE:POIN %i, "%points)+portString+"\n")
        dev.write(("SOUR:SWE:DWEL %f, "%dwell)+portString+"\n")
        for i, port in enumerate(ports):
            dev.write("SOUR%i:SWE:STAR %f\n"%(port,start_vs[i]))
            dev.write("SOUR%i:SWE:STOP %f\n"%(port,end_vs[i]))
        dev.write("SOUR%i:DC:MARK:SSTART:TNUM 1\n"%(ports[0])) #tie internal trigger 1 to every step of the sweep on first channel (channel choice is arbitrary)
        dev.write("OUTP:TRIG%i:SOUR INT1\n"%(trig)) #tie the TTL pulse to the internal trigger 1
        dev.write("OUTP:TRIG%i:WIDTH %f\n"%(trig,ttlwidth))
        dev.write("SOUR:DC:TRIG:SOUR INT2, "+portString+"\n")#Trigger all sweeps when internal 2 is fired
        dev.write("SOUR:DC:INIT "+portString+"\n")
        ans=yield dev.write("TINT 2\n") #trigger internal trigger 2
        returnValue(ans)
    
    @setting(116,ports='*i',start_vs='*v',end_vs='*v',points='i',dwell='v')
    def ramp(self,c,ports,start_vs,end_vs,points,dwell):
        """
        Sweeps multiple channels from start to end voltages, at the given dwell time in s
        No TTL output is triggered during the sweep
        """
        dev=self.selectedDevice(c)
        portString = '(@'+','.join([str(e) for e in ports])+')'
        dev.write("SOUR:DC:VOLT:MODE SWE, "+portString+"\n")
        dev.write("SOUR:SWE:COUN 1, "+portString+"\n")
        dev.write(("SOUR:SWE:POIN %i, "%points)+portString+"\n")
        dev.write(("SOUR:SWE:DWEL %f, "%dwell)+portString+"\n")
        for i, port in enumerate(ports):
            dev.write("SOUR%i:SWE:STAR %f\n"%(port,start_vs[i]))
            dev.write("SOUR%i:SWE:STOP %f\n"%(port,end_vs[i]))
        dev.write("SOUR:DC:TRIG:SOUR INT2, "+portString+"\n")#Trigger all sweeps when internal 2 is fired
        dev.write("SOUR:DC:INIT "+portString+"\n")
        ans=yield dev.write("TINT 2\n") #trigger internal trigger 2
        returnValue(ans)
        
    @setting(108,port='i',start='v',end='v',points='i',dwell='v')
    def ramp1(self,c,port,start,end,points,dwell):
        """
        Sweeps a single channel from start to end voltage, at the given dwell time in s
        No TTL output is triggered during the sweep
        """
        dev=self.selectedDevice(c)
        dev.write("SOUR%i:DC:VOLT:MODE SWE\n"%(port))
        dev.write("SOUR%i:SWE:STAR %f\n"%(port,start))
        dev.write("SOUR%i:SWE:STOP %f\n"%(port,end))
        dev.write("SOUR%i:SWE:COUN 1\n"%(port))
        dev.write("SOUR%i:SWE:POIN %i\n"%(port,points))
        dev.write("SOUR%i:SWE:DWEL %f\n"%(port,dwell))
        ans=yield dev.write("SOUR%i:DC:INIT\n"%(port))
        returnValue(ans)
    
    @setting(109,port='i',freq='v',ampl='v',cycles='s')
    def start_sine(self,c,port,freq,ampl,cycles=-1):
        """
        Starts outputting a sine wave with given fequency and peak-to-peak amplitude.
        By deafult ouputs until explicitly stopped - specify an integer 'cycles' to output only a finite number of periods
        """
        dev=self.selectedDevice(c)
        #Change the filters and output range to high for maximum bandwidth
        dev.write("SOUR%i:FILT:HIGH\n"%(port))
        dev.write("SOUR%i:RANG:HIGH\n"%(port))
        dev.write("SOUR%i:RANG:HIGH\n"%(port))
        dev.write("SOUR%i:SINE:FREQ %f\n"%(port,freq))
        dev.write("SOUR%i:SINE:SPAN %f\n"%(port,ampl))
        if (cycles!=-1):
            dev.write("SOUR%i:SINE:COUN %i\n"%(port,cycles))
        else:
            dev.write("SOUR%i:SINE:COUN INF\n"%(port))
        dev.write("SOUR%i:SINE:TRIG:SOUR IMM\n"%(port))
        ans=yield dev.write("SOUR%i:SINE:INIT:IMM\n"%(port))
        returnValue(ans)
        
    @setting(110,port='i')
    def stop_sine(self,c,port):
        """
        Starts outputting a sine wave with given fequency and peak-to-peak amplitude.
        By deafult ouputs until explicitly stopped - specify an integer 'cycles' to output only a finite number of periods
        """
        dev=self.selectedDevice(c)
        #Change the filters and output range to high for maximum bandwidth
        ans=yield dev.write("SOUR%i:SINE:ABORT\n"%(port))
        returnValue(ans)
    
    @setting(111,port='i',freq='v',ampl='v',cycles='i')
    def start_tri(self,c,port,freq,ampl,cycles=-1):
        """
        Starts outputting a triangle wave with given fequency and peak-to-peak amplitude.
        By default ouputs until explicitly stopped - specify an integer 'cycles' to output only a finite number of periods
        """
        dev=self.selectedDevice(c)
        #Change the filters and output range to high for maximum bandwidth
        dev.write("SOUR%i:FILT:HIGH\n"%(port))
        dev.write("SOUR%i:RANG:HIGH\n"%(port))
        dev.write("SOUR%i:RANG:HIGH\n"%(port))
        dev.write("SOUR%i:TRI:FREQ %f\n"%(port,freq))
        dev.write("SOUR%i:TRI:SPAN %f\n"%(port,ampl))
        if (cycles!=-1):
            dev.write("SOUR%i:TRI:COUN %i\n"%(port,cycles))
        else:
            dev.write("SOUR%i:TRI:COUN INF\n"%(port))
        dev.write("SOUR%i:TRI:TRIG:SOUR IMM\n"%(port))
        ans=yield dev.write("SOUR%i:TRI:INIT:IMM\n"%(port))
        returnValue(ans)
        
    @setting(112,port='i')
    def stop_tri(self,c,port):
        """
        Stop outputting a triangle wave on the specified channel
        """
        dev=self.selectedDevice(c)
        #Change the filters and output range to high for maximum bandwidth
        ans=yield dev.write("SOUR%i:TRI:ABORT\n"%(port))
        returnValue(ans)
        
    @setting(113,port='i',freq='v',ampl='v',cycles='i')
    def start_squ(self,c,port,freq,ampl,cycles=-1):
        """
        Starts outputting a square wave with given fequency and peak-to-peak amplitude.
        By default ouputs until explicitly stopped - specify an integer 'cycles' to output only a finite number of periods
        """
        dev=self.selectedDevice(c)
        #Change the filters and output range to high for maximum bandwidth
        dev.write("SOUR%i:FILT:HIGH\n"%(port))
        dev.write("SOUR%i:RANG:HIGH\n"%(port))
        dev.write("SOUR%i:RANG:HIGH\n"%(port))
        dev.write("SOUR%i:SQU:FREQ %f\n"%(port,freq))
        dev.write("SOUR%i:SQU:SPAN %f\n"%(port,ampl))
        if (cycles!=-1):
            dev.write("SOUR%i:SQU:COUN %i\n"%(port,cycles))
        else:
            dev.write("SOUR%i:SQU:COUN INF\n"%(port))
        dev.write("SOUR%i:SQU:TRIG:SOUR IMM\n"%(port))
        ans=yield dev.write("SOUR%i:SQU:INIT:IMM\n"%(port))
        returnValue(ans)
        
    @setting(114,port='i')
    def stop_squ(self,c,port):
        """
        Stop outputting a square wave on the specified channel
        """
        dev=self.selectedDevice(c)
        #Change the filters and output range to high for maximum bandwidth
        ans=yield dev.write("SOUR%i:SQU:ABORT\n"%(port))
        returnValue(ans)

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

__server__ = qdacServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
