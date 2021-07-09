
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
name = CXA N9000 Spectrum Analyzer
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
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue
import labrad.units as units
from labrad.types import Value
import numpy as np

TIMEOUT = Value(5,'s')
BAUD    = 9600

class CXA_N9000_Wrapper(GPIBDeviceWrapper):      
    pass
        
class CXA_N9000_Server(GPIBManagedServer):
    name = 'CXA N9000'
    deviceName = 'Agilent Technologies N9000A'
    deviceWrapper = CXA_N9000_Wrapper

    @setting(101, mode='i',returns='s')
    def ident(self,c,mode):
        dev=self.selectedDevice(c)
        ans = yield dev.query('*IDN?')
        returnValue(ans)
        
    @setting(102, freq='v[]')
    def set_frequency_start(self,c,freq):
        '''Sets the lower bound of the frequency range to be analyzed. Frequency in Hz.'''
        dev=self.selectedDevice(c)
        ans = yield dev.write('FREQuency:STARt ' + str(freq))
        
    @setting(103, returns='v[]')
    def get_frequency_start(self,c):
        '''Gets the lower bound of the frequency range to be analyzed. Frequency in Hz.'''
        dev=self.selectedDevice(c)
        ans = yield dev.query('FREQuency:STARt?')
        returnValue(float(ans))
        
    @setting(104, freq='v[]')
    def set_frequency_stop(self,c,freq):
        '''Sets the upper bound of the frequency range to be analyzed. Frequency in Hz.'''
        dev=self.selectedDevice(c)
        ans = yield dev.write('FREQuency:STOP ' + str(freq))
        
    @setting(105, returns='v[]')
    def get_frequency_stop(self,c):
        '''Gets the upper bound of the frequency range to be analyzed. Frequency in Hz.'''
        dev=self.selectedDevice(c)
        ans = yield dev.query('FREQuency:STOP?')
        returnValue(float(ans))
        
    @setting(106, freq='v[]')
    def set_frequency_center(self,c,freq):
        '''Sets the center of the frequency range to be analyzed.'''
        dev=self.selectedDevice(c)
        ans = yield dev.write('FREQuency:CENTer ' + str(freq))
        
    @setting(107, returns='v[]')
    def get_frequency_center(self,c):
        '''Gets the center of the frequency range to be analyzed.'''
        dev=self.selectedDevice(c)
        ans = yield dev.query('FREQuency:CENTer?')
        returnValue(float(ans))
        
    @setting(108, freq='v[]') 
    def set_frequency_span(self,c,freq):
        '''Sets the span of the frequency range to be analyzed around the central frequency.'''
        dev=self.selectedDevice(c)
        ans = yield dev.write('FREQuency:SPAN ' + str(freq))
        
    @setting(109, returns='v[]')
    def get_frequency_span(self,c):
        '''Gets the span of the frequency range to be analyzed around the central frequency.'''
        dev=self.selectedDevice(c)
        ans = yield dev.query('FREQuency:SPAN?')
        returnValue(float(ans))
    
    @setting(110, freq='v[]') 
    def set_bandwidth_freq(self,c,freq):
        '''Sets the bandwidth of the frequency meaurements.'''
        dev=self.selectedDevice(c)
        ans = yield dev.write('BAND ' + str(freq))
        
    @setting(111, returns='v[]')
    def get_bandwidth_freq(self,c):
        '''Gets the bandwidth of the frequency meaurements.'''
        dev=self.selectedDevice(c)
        ans = yield dev.query('BAND?')
        returnValue(float(ans))   
    
    @setting(112, mode ='i') 
    def set_bandwidth_mode(self,c,mode):
        '''Sets the bandwidth of the frequency meaurements to be either automatic (1) or manual (0). If manual, desired bandwidth should be set with 
        set bandwidth freq command. If automatic, bandwidth ratio should be set with the set bandwidth ratio command.'''
        dev=self.selectedDevice(c)
        ans = yield dev.write('BWID:AUTO ' + str(mode))
        
    @setting(113, returns='i')
    def get_bandwidth_mode(self,c):
        '''Gets the bandwidth of the frequency meaurements to be either automatic (1) or manual (0). If manual, desired bandwidth should be set with 
        set bandwidth freq command. If automatic, bandwidth ratio should be set with the set bandwidth ratio command.'''
        dev=self.selectedDevice(c)
        ans = yield dev.query('BWID:AUTO?')
        returnValue(int(ans)) 
    
    @setting(114, ratio='i') 
    def set_bandwidth_ratio(self,c,ratio = None):
        '''Sets the bandwidth ratio of the frequency meaurements to the span of the measurement being made. If passed without specifying a ratio, 
        will choose the ratio automatically.'''
        dev=self.selectedDevice(c)
        if ratio is not None:
            ans = yield dev.write('FREQ:SPAN:BAND:RAT ' + str(freq))
        else:
            yield dev.write('FREQ:SPAN:BAND:RAT:AUTO 1')
            
    @setting(115, returns = 'i') 
    def get_bandwidth_ratio(self,c):
        '''Gets the bandwidth ratio of the frequency meaurements to the span of the measurement being made.'''
        dev=self.selectedDevice(c)
        ans = yield dev.query('FREQ:SPAN:BAND:RAT?')
    
    @setting(116, num ='i') 
    def set_trace_avg(self,c,num):
        '''Sets the number of traces to be averaged for a single measurement.'''
        dev=self.selectedDevice(c)
        ans = yield dev.write('AVER:COUN ' + str(num))
        
    @setting(117, returns='i')
    def get_trace_avg(self,c):
        '''Gets the number of traces to be averaged for a single measurement.'''
        dev=self.selectedDevice(c)
        ans = yield dev.query('AVER:COUN?')
        returnValue(int(ans)) 
        
    @setting(118, num ='i') 
    def set_trace_points(self,c,num):
        '''Sets the number of points to be taken per trace.'''
        dev=self.selectedDevice(c)
        ans = yield dev.write('SWE:POIN ' + str(num))
        
    @setting(119, returns='i')
    def get_trace_points(self,c):
        '''Gets the number of points to be taken per trace.'''
        dev=self.selectedDevice(c)
        ans = yield dev.query('SWE:POIN?')
        returnValue(int(ans)) 
        
    @setting(120, returns='**v[]')
    def get_trace(self,c):
        '''Retrieves the trace data. Does NOT run a sweep; just returns the data of whatever is currently on the screen. Returns 2D array with frequency as one dimension, and voltage (in units specified by the set units command) as the other.'''
        dev=self.selectedDevice(c)
        yield dev.write('FORMat:DATA ASCIi')
        data = yield dev.query(':TRAC? TRACE1')
        data = data.split(',')
        
        start = yield self.get_frequency_start(c)
        stop = yield self.get_frequency_stop(c)
        data_length = len(data)

        freqs = np.linspace(start,stop,data_length)
        
        trace_data = []
        for i in range (0,data_length):
            trace_data.append([freqs[i], float(data[i])])
        returnValue(trace_data) 
        
    @setting(121)
    def start_single(self,c):
        '''Takes a new single data set.'''
        dev=self.selectedDevice(c)
        yield dev.write(':INIT:CONT 0')
        yield dev.write(':INIT:REST')
 
    @setting(122, returns = 'i')
    def get_sweeping_status(self,c):
        '''Returns Operation Status Register (view documentation for clarification).'''
        dev=self.selectedDevice(c)
        ans = yield dev.query('STAT:OPER:COND?')
        returnValue(int(ans))
       
    @setting(123, returns='**v[]')
    def record_trace(self,c):
        '''Starts are new trace and records the data. This method does run a sweep. Returns 2D array with frequency as one dimension, and voltage (in units specified by the signal analyzer) as the other.'''
        dev=self.selectedDevice(c)
        yield self.start_single(c)
        while True:
            status = yield self.get_sweeping_status(c)
            if status == 0:
                break
                
        ans = yield self.get_trace(c)
        returnValue(ans)        
        
    
__server__ = CXA_N9000_Server()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)