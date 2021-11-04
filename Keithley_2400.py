# AFY servers
# Keithley K2400
# Joshua Island 2017

"""
### BEGIN NODE INFO
[info]
name = Keithley Server 2400
version = 1.0
description =

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

from labrad.server import setting
from labrad.gpib import GPIBManagedServer
from twisted.internet.defer import inlineCallbacks, returnValue
import time
import numpy as np


class K2400(GPIBManagedServer):
    name = 'K2400'  # Server name
    deviceName = 'KEITHLEY INSTRUMENTS INC. MODEL 2400'  # Model string returned from *IDN?

    @setting(111, volts='v', returns='v')
    def set_volts(self, c, volts, compl = 1e-6):
        dev = self.selectedDevice(c)
        yield dev.write('SOUR:VOLT ' + str(volts))
        yield dev.write(':SENSe:CURRent:PROTection ' + str(compl))
        voltage = yield dev.query('MEAS:VOLT:DC?')
        voltage = (voltage.split(',')[0] )
        returnValue(float(voltage))
        #returnValue(voltage)

    @setting(112, returns='v')
    def get_volts(self, c):
        dev = self.selectedDevice(c)
        yield dev.write(':OUTPUT ON')
        voltage = yield dev.query(':READ?')
        voltage = voltage[1:12]
        returnValue(voltage)

    @setting(113, volts='v', returns='v')
    def set_v_meas_i(self, c, volts, compl = 1e-6, autorange = 0):
        dev = self.selectedDevice(c)
        yield dev.write('SOUR:VOLT ' + str(volts))
        # not rigorously tested
        if (autorange == 1):
            yield dev.write(':SENSe:CURRent:RANGe:AUTO ON')
        else:
            yield dev.write(':SENSe:CURRent:RANGe:AUTO OFF')

        yield dev.write(':SENSe:CURRent:PROTection ' + str(compl))
        current = yield dev.query('MEAS:CURR:DC?')
        current = (current.split(',')[1] )
        returnValue(float(current))
    
    @setting(116)
    def output_on(self, c):
        dev = self.selectedDevice(c)
        yield dev.write(':OUTP ON')     
        returnValue(1)
        
    @setting(117)
    def output_off(self, c):
        dev = self.selectedDevice(c)
        yield dev.write(':OUTP OFF')     
        returnValue(1)
        
    @setting(118, returns = 'v')
    def read_v(self, c):
        dev = self.selectedDevice(c)
        data = yield dev.query('MEAS:CURR:DC?')   
        volts = (data.split(',')[0] )  
        returnValue( float(volts) )
        
    @setting(119, returns = 'v')
    def read_i(self, c):
        dev = self.selectedDevice(c)
        data = yield dev.query('MEAS:CURR:DC?')
        current = (data.split(',')[1] )   
        returnValue( float(current) )
    
    @setting(120, returns = [] )
    def ramp_volt_SPCI(self,  c, start_num , stop_num, step_num, compl = 1e-6 ):        
        dev = self.selectedDevice(c) 
        trace_point = 10
        yield dev.write('*RST')
        yield dev.write(':SENS:FUNC:CONC ON')
        yield dev.write(':SOUR:FUNC VOLT')
        yield dev.write(':SENSe:CURRent:PROTection ' + str(compl))
        yield dev.write(':SENS:FUNC "CURR"') #error in line
        yield dev.write(':SOUR:VOLT:START '+str(start_num)) #  in volts bounds -200 to 200       
        yield dev.write(':SOUR:VOLT:STOP '+str(stop_num))#  in volts bounds -200 to 200
        yield dev.write(':SOUR:VOLT:STEP '+str(step_num))#  in volts bounds -200 to 200
        trig_num = -(start_num - stop_num)/step_num +1
        yield dev.write(':SOUR:VOLT:MODE SWE')
        yield dev.write(':SOUR:SWE:RANG AUTO')
        yield dev.write(':SOUR:SWE:SPAC LIN')
        yield dev.write(':TRIG:COUN '+str(trig_num))
        yield dev.write(':SOUR:DEL 0.1') #THIS IS THE AMOUNT OF DELAY 
        #Storing the readings in buffer       
        yield dev.write(':TRAC:CLEar')
        yield dev.write(':TRAC:FEED SENS')
        yield dev.write(':TRAC:POIN '+str(trig_num))
        yield dev.write(':TRAC:FEED:CONT NEXT')
        yield dev.write(':TRIG:COUN '+str(trig_num))
        yield dev.write(':OUTP ON') #MEASure OUTP ON  #running up to here       
        yield dev.write(':INIT')
        print('Read complete')
        time.sleep(trig_num*0.2) 
        #sleep during measurment 
        yield dev.write(':OUTP OFF')
        num_values = yield dev.query(':TRAC:POIN:ACT?') #tells us how many measurments are there 
        data = yield dev.query(':TRAC:DATA?')
        #pulls data 
        yield dev.write(':TRAC:CLE')
        #current array 
        current = []
        x=0
        n=trig_num
        while x<n:
            current.append(float ( (data.split(',')[1+(x*5)])) )
            x= x+1
        #voltage array 
        voltage = []
        j=0
        n=trig_num
        while j<n:
            voltage.append((data.split(',')[(j*5)]))
            j= j+1
        print(current)
        returnValue( (current) )
        
    @setting(121, returns = [])
    def ramp_current_SPCI(self,  c, start_num , stop_num, step_num, compl = 50e-6 ):        
        dev = self.selectedDevice(c) 
        yield dev.write('*RST')
        yield dev.write(':SENS:FUNC:CONC ON')
        yield dev.write(':SOUR:FUNC CURR')
        yield dev.write(':SENSe:CURR:PROTection ' + str(compl))
        yield dev.write(':SENS:FUNC "VOLT:DC"') #error in line
        yield dev.write(':SOUR:CURR:START '+str(start_num)) #  in volts bounds -200 to 200       
        yield dev.write(':SOUR:CURR:STOP '+str(stop_num))#  in volts bounds -200 to 200
        yield dev.write(':SOUR:CURR:STEP '+str(step_num))#  in volts bounds -200 to 200
        trig_num = -(start_num - stop_num)/step_num +1
        yield dev.write(':SOUR:CURR:MODE SWE')
        yield dev.write(':SOUR:SWE:RANG AUTO')
        yield dev.write(':SOUR:SWE:SPAC LIN')
        yield dev.write(':TRIG:COUN '+str(trig_num))
        yield dev.write(':SOUR:DEL 0.1')  #THIS IS THE AMOUNT OF DELAY 
        #Storing the readings in buffer       
        yield dev.write(':TRAC:CLEar')
        yield dev.write(':TRAC:FEED SENS')
        yield dev.write(':TRAC:POIN '+str(trig_num))
        yield dev.write(':TRAC:FEED:CONT NEXT')
        yield dev.write(':TRIG:COUN '+str(trig_num))
        yield dev.write(':OUTP ON') #MEASure OUTP ON  #running up to here       
        yield dev.write(':INIT')
        print('Read complete')
        time.sleep(trig_num*0.2) 
        #sleep during measurment 
        yield dev.write(':OUTP OFF')
        num_values = yield dev.query(':TRAC:POIN:ACT?') #tells us how many measurments are there 
        data = yield dev.query(':TRAC:DATA?')
        #pulls data 
        yield dev.write(':TRAC:CLE')
        #current array 
        current = []
        x=0
        n=trig_num
        while x<(n-1):
            current.append((data.split(',')[1+(x*5)]))
            x= x+1
        #voltage array 
        voltage = []
        j=0
        n=trig_num
        while j<(n-1):
            voltage.append( float(data.split(',')[(j*5)]))
            j= j+1

        returnValue( voltage )
     
            
    @setting(122, returns = [])
    def average_over_volt(self,  c, volt , trig_num , delay = 0.1, compl = 50e-6 ):        
        dev = self.selectedDevice(c)
        
        str_volts =  str(volt)+','
        x = 2 
        while x< trig_num:
            str_volts = str_volts + str(volt)+','
            x =x +1
        str_volts = str_volts + str(volt)
    
        yield dev.write('*RST')
        yield dev.write(':TRAC:CLEar')
        yield dev.write(':SENS:FUNC:CONC ON')
        yield dev.write(':SOUR:FUNC VOLT')
        yield dev.write(':SENS:FUNC "CURR"')
        yield dev.write(':SENSe:CURR:PROTection ' + str(compl))
        
        yield dev.write(':SOUR:VOLT:MODE LIST')
        yield dev.write(':SOUR:LIST:VOLT '+str_volts)
        yield dev.write(':TRIG:COUN '+str(trig_num)) 
        yield dev.write(':SOUR:DEL '+str(delay)) 

        yield dev.write(':TRAC:CLEar')
        yield dev.write(':TRAC:FEED SENS')
        yield dev.write(':TRAC:POIN '+str(trig_num))
        yield dev.write(':TRAC:FEED:CONT NEXT')
        yield dev.write(':TRIG:COUN '+str(trig_num))
        yield dev.write(':OUTP ON') #MEASure OUTP ON  #running up to here       
        yield dev.write(':INIT')
        print('Read complete')
        time.sleep(trig_num*0.2) 
        data = yield dev.query(':TRACE:DATA?')
        yield dev.write(':OUTP OFF')
        yield dev.write(':CALC3:FORM MEAN')
        data_mean = yield dev.query(':CALC3:DATA?')
        mean = float(data_mean.split(',')[1])
        yield dev.write(':CALC3:FORM SDEV')
        dev = yield dev.query(':CALC3:DATA?')
        standard_dev = float(dev.split(',')[1])

#        yield dev.write(':TRAC:CLEar')
        returnValue( [mean,standard_dev] )
    
    @setting(123, returns = [])    
    def average_over_current(self,  c, current , trig_num , delay = 0.1, compl = 50e-6 ):        
        dev = self.selectedDevice(c)
        
        str_current =  str(current)+','
        x = 2 
        while x< trig_num:
            str_current = str_current + str(current)+','
            x =x +1
        str_current = str_current + str(current)
       
        yield dev.write('*RST')
        yield dev.write(':TRAC:CLEar')
        yield dev.write(':SENS:FUNC:CONC ON')
        yield dev.write(':SOUR:FUNC CURR')
        yield dev.write(':SENS:FUNC "VOLT:DC"')
        yield dev.write(':SENSe:CURR:PROTection ' + str(compl))
        
        yield dev.write(':SOUR:CURR:MODE LIST')
        yield dev.write(':SOUR:LIST:CURR '+str_current)
        yield dev.write(':TRIG:COUN '+str(trig_num)) 
        yield dev.write(':SOUR:DEL '+str(delay)) 

        yield dev.write(':TRAC:CLEar')
        yield dev.write(':TRAC:FEED SENS')
        yield dev.write(':TRAC:POIN '+str(trig_num))
        yield dev.write(':TRAC:FEED:CONT NEXT')
        yield dev.write(':TRIG:COUN '+str(trig_num))
        yield dev.write(':OUTP ON') #MEASure OUTP ON  #running up to here       
        yield dev.write(':INIT')
        print('Read complete')
        time.sleep(trig_num*0.2) 
        data = yield dev.query(':TRACE:DATA?')
        yield dev.write(':OUTP OFF')
        yield dev.write(':CALC3:FORM MEAN')
        data_mean = yield dev.query(':CALC3:DATA?')
        mean = float(data_mean.split(',')[0])
        yield dev.write(':CALC3:FORM SDEV')
        dev = yield dev.query(':CALC3:DATA?')
        standard_dev = float(dev.split(',')[0])

#        yield dev.write(':TRAC:CLEar')
        returnValue( [mean,standard_dev] )    
        
__server__ = K2400()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
