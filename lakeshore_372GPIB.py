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
name = lakeshore_372
version = 1.0
description = Lake Shore AC Resistance Bridge and Temperature Controller
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
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as units
from labrad.types import Value

TIMEOUT = Value(5,'s')
BAUD    = 57600
PARITY = 'O'
STOP_BITS = 1
BYTESIZE= 7


class Lakeshore372Wrapper(GPIBDeviceWrapper):
    @inlineCallbacks
    def idn(self):
        ans = yield self.query("*IDN?")
        returnValue(ans)
    
    @inlineCallbacks
    def read_temp(self, channel):
        ans = yield self.query("KRDG?%s" %channel)
        returnValue(ans)
    
    @inlineCallbacks
    def setpoint(self, channel, p):
        yield self.write("SETP%i,%f"%(channel, p))
    
    @inlineCallbacks
    def setpoint_read(self, channel):
        ans = yield self.query("SETP?%i" %channel)
        returnValue(ans)
    
    @inlineCallbacks
    def heater_pct(self, channel):
        ans = yield self.query("HTR?%s" %channel)
        returnValue(ans)
    
    @inlineCallbacks
    def range_set(self, channel, range):
        yield self.write("RANGE%i,%i" %(channel, range))
    
    @inlineCallbacks
    def range_read(self, channel):
        ans = yield self.query("RANGE?%i" %channel)
        returnValue(ans)
    
    @inlineCallbacks
    def heater_set(self, channel, resistance, max_current, max_user_current, output_display):
        yield self.write("HTRSET%s,%s,%s,%s,%s" %(channel, resistance, max_current, max_user_current, output_display))
    
    @inlineCallbacks
    def heater_read(self, channel):
        ans = yield self.query("HTRSET?%i" %channel)
        returnValue(ans)
    
        
class Lakeshore372Server(GPIBManagedServer):
    name = 'lakeshore_372'
    deviceName = 'LSCI MODEL372'
    # deviceIdentFunc = 'identify_device'
    deviceWrapper = Lakeshore372Wrapper
 
    @setting(9988, server='s', address='s')
    def identify_device(self, c, server, address):
        print('identifying:', server, address)
        try:
            s = self.client[server]
            p = s.packet()
            p.address(address)
            p.write_termination('\r')
            p.read_termination('\r')
            p.write('V')
            p.read()
            p.write('V')
            p.read()
            ans = yield p.send()
            resp = ans.read[1]
            print('got ident response:', resp)
            if resp == 'LSCI,MODEL372,LSA13DP,1.3':
                returnValue(self.deviceName)

        except Exception as e:
            print('failed:', e)
            raise

    @setting(101, returns='s')
    def ID(self, c):
        """
        Identifies the device, response should be 'LSCI,MODEL372,LSA13DP,1.3'.
        """
        dev=self.selectedDevice(c)
        ans = yield dev.idn()
        returnValue(ans)
    
    @setting(102, channel='s',returns='s')
    def read_temp(self, c, channel):
        """
        Reads the temperature at an input in degrees Kelvin. Input channels are labeled by letters 'A' - 'D'.
        """
        dev=self.selectedDevice(c)
        ans = yield dev.read_temp(channel)
        returnValue(ans)
    
    @setting(103, channel = 'i', p = 'v')
    def setpoint(self, c, channel, p):
        """
        Sets the temperature setpoint for a specified output.
        """
        dev=self.selectedDevice(c)
        yield dev.setpoint(channel, p)
    
    @setting(104, channel = 'i', returns='s')
    def setpoint_read(self, c, channel):
        """
        Reads the temperature setpoint for a specified output.
        """
        dev=self.selectedDevice(c)
        ans = yield dev.setpoint_read(channel)
        returnValue(ans)
        
    @setting(105, channel = 'i', returns='s')
    def heater_pct(self, c, channel):
        """
        Returns the heater output in percent for a specified output.
        """
        dev=self.selectedDevice(c)
        ans = yield dev.heater_pct(channel)
        returnValue(ans)
    
    @setting(106, channel = 'i', range = 'i')
    def range_set(self, c, channel, range):
        """
        Sets the range for a specified output. Outputs 1 and 2 have 5 available ranges, and outputs 3 and 4 are either 0 = off or 1 = on.
        """
        dev=self.selectedDevice(c)
        yield dev.range_set(channel, range)
        
    @setting(107, channel = 'i', returns='s')
    def range_read(self, c, channel):
        """
        Reads the range for a specified output. Refer to the documentation for range_set for a description of the return value.
        """
        dev=self.selectedDevice(c)
        ans = yield dev.range_read(channel)
        returnValue(ans)
    
    @setting(108, channel='i', resistance='i',max_current='i', max_user_current='v',output_display='i')
    def heater_set(self,c,channel,resistance,max_current,max_user_current,output_display):
        dev=self.selectedDevice(c)
        yield dev.heater_set(channel,resistance,max_current,max_user_current,output_display)
        
    @setting(109, channel = 'i', returns='s')
    def heater_read(self, c, channel):
        """
        Reads the heater output setting for a specified output (the meaning of the returned list is documented in heater_set).
        """
        dev=self.selectedDevice(c)
        ans = yield dev.heater_read(channel)
        returnValue(ans)
    
    @setting(110, returns='v', setpt = 'v')
    def mc(self,c,setpt=None):
        dev=self.selectedDevice(c)
        if setpt is None:
            ans = yield dev.read_temp(6)
            returnValue(ans)
        else:
            #this is not setup to work yet
            yield dev.setpoint(0, setpt)
            ans = yield dev.setpoint_read(0)
            returnValue(float(ans))
    
    @setting(111, returns='v', setpt='v')
    def probe(self,c, setpt=None):
        dev=self.selectedDevice(c)
        if setpt is None:
            ans = yield dev.read_temp(9)
            returnValue(ans)
        else:
            #this is not setup to work yet
            yield dev.setpoint(0, setpt)
            ans = yield dev.setpoint_read(0)
            returnValue(float(ans))
    
    @setting(112)
    def htr_off(self,c):
        dev=self.selectedDevice(c)
        yield dev.setpoint(0,0.0)
        yield dev.heater_set(0,0)
    
    @setting(113, in_channel='i')
    def channel_off(self,c, in_channel):
        """
        turn off an input channel
        """
        dev = self.selectedDevice(c)
        yield dev.write("INSET %s,0\n"%in_channel)
    
    @setting(114, in_channel='i', dwell = 'i', pause = 'i', curve = 'i', tempco='i' ,returns='s')
    def channel_on(self,c, in_channel, dwell=7, pause=3, curve=0, tempco=2):
        """
        turn on an input channel
        """
        dev=self.selectedDevice(c)
        """default value of curve is 0 or the values correspondant to certain in_channels as given in the following dictionary. However, the default is overwritten if user specifies a non-zero value"""
        crvs = {
            1: 21,
            2: 22,
            3: 23,
            5: 25,
            6: 26,
            9: 29
        }
        crv = crvs.get(in_channel)
        if crv != None and curve==0:
            curve = crv
        yield dev.write("INSET %s,1,%s,%s,%s,%s\n"%(in_channel, dwell, pause, curve, tempco))
        yield dev.write("KRDG? %s\n"%in_channel)
        ans = yield dev.read()
        returnValue(ans)
    
    @setting(115, out_percent='v')
    def still_out(self,c, out_percent):
        """
        specify a power in percentage for the still/analog heater
        """
        dev = self.selectedDevice(c)
        yield dev.write("STILL %s\n"%out_percent)
    
    @setting(116)
    def still_off(self,c):
        """
        turn off the still/analog heater
        """
        dev = self.selectedDevice(c)
        yield dev.write("RANGE 2,0\n")
    
    @setting(117)
    def still_on(self,c):
        """
        turn on the still/analog heater
        """
        dev = self.selectedDevice(c)
        yield dev.write("RANGE 2,1\n")
    
    @setting(118,returns='s')
    def still_read(self,c):
        dev = self.selectedDevice(c)
        yield dev.write("STILL? \n")
        ans = yield dev.read()
        returnValue(ans)
    
    @setting(119, output='i', stat='i', rate='s')
    def ramp_set(self,c, output, stat, rate):
        dev = self.selectedDevice(c)
        yield dev.write("RAMP %i,%i,%f\n"%(output, stat, rate))
    
    @setting(120, output='i', returns='s')
    def ramp_read(self,c, output):
        dev = self.selectedDevice(c)
        yield dev.write("RAMP? %i\n"%output)
        ans = yield dev.read()
        returnValue(ans)
    
    
__server__ = Lakeshore372Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
