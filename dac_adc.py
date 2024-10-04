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
name = DAC-ADC
version = 1.2.0
description = DAC-ADC Box server: AD5764-AD7734, AD5780-AD7734, AD5791-AD7734
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
# import labrad.units as units
from labrad.types import Value
import numpy as np
import time
# from exceptions import IndexError

TIMEOUT = Value(5,'s')
BAUD    = 10000

def twoByteToInt(DB1,DB2): # This gives a 16 bit integer (between +/- 2^16)
  return 256*DB1 + DB2

def map2(x, in_min, in_max, out_min, out_max):
  return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;


class DAC_ADCWrapper(DeviceWrapper):
    channels = [0,1,2,3]

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

    def setramping(self, state):
        self.ramping = state

    def isramping(self):
        return self.ramping

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
    def readByte(self,count):
        p=self.packet()
        p.readbyte(count)
        ans=yield p.send()
        returnValue(ans.readbyte)

    @inlineCallbacks
    def in_waiting(self):
        p = self.packet()
        p.in_waiting()
        ans = yield p.send()
        returnValue(ans.in_waiting)

    @inlineCallbacks
    def reset_input_buffer(self):
        p = self.packet()
        p.reset_input_buffer()
        ans = yield p.send()
        returnValue(ans.reset_input_buffer)

    @inlineCallbacks
    def timeout(self, time):
        yield self.packet().timeout(time).send()

    @inlineCallbacks
    def query(self, code):
        """ Write, then read. """
        p = self.packet()
        p.write_line(code)
        p.read_line()
        ans = yield p.send()
        returnValue(ans.read_line)



class DAC_ADCServer(DeviceServer):
    name = 'DAC-ADC'
    deviceName = 'Arduino DAC-ADC'
    deviceWrapper = DAC_ADCWrapper

    channels = [0,1,2,3]

    sPrefix = 703000
    sigInputRead         = Signal(sPrefix+0,'signal__input_read'         , '*s') #
    sigOutputSet         = Signal(sPrefix+1,'signal__output_set'         , '*s') #
    sigRamp1Started      = Signal(sPrefix+2,'signal__ramp_1_started'     , '*s') #
    sigRamp2Started      = Signal(sPrefix+3,'signal__ramp_2_started'     , '*s') #
    sigConvTimeSet       = Signal(sPrefix+4,'signal__conversion_time_set', '*s') #
    sigBufferRampStarted = Signal(sPrefix+5,'signal__buffer_ramp_started', '*s') #

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
        yield reg.cd(['', 'Servers', 'dac_adc', 'Links'], True)
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
            #print(server)
            #print(port)
            ports = yield server.list_serial_ports()
            #print(ports)
            if port not in ports:
                continue
            devName = '%s (%s)' % (name, port)
            devs += [(devName, (server, port))]

       # devs += [(0,(3,4))]
        returnValue(devs)


    @setting(100)
    def connect(self,c,server,port):
        dev=self.selectedDevice(c)
        yield dev.connect(server,port)

    @setting(103,port='i',voltage='v',returns='s')
    def set_voltage(self,c,port,voltage):
        """
        SET sets a voltage to a channel and returns the channel and the voltage it set.
        """
        if not (port in range(4)):
            returnValue("Error: invalid port number.")
            return
        if (voltage > 10) or (voltage < -10):
            returnValue("Error: invalid voltage. It must be between -10 and 10.")
            return
        dev=self.selectedDevice(c)
        yield dev.write("SET,%i,%f\r\n"%(port,voltage))
        ans = yield dev.read()
        voltage=ans.lower().partition(' to ')[2][:-1]
        self.sigOutputSet([str(port),voltage])
        returnValue(ans)


    @setting(104,port='i',returns='v[]')
    def read_voltage(self,c,port):
        """
        GET_ADC returns the voltage read by an input channel. Do not confuse with GET_DAC; GET_DAC has not been implemented yet.
        """
        dev=self.selectedDevice(c)
        if not (port in range(8)):
            returnValue("Error: invalid port number.")
            return
        yield dev.write("GET_ADC,%i\r\n"%port)
        ans = yield dev.read()
        self.sigInputRead([str(port),str(ans)])
        returnValue(float(ans))

    @setting(105,port='i',ivoltage='v',fvoltage='v',steps='i',delay='i',returns='s')
    def ramp1(self,c,port,ivoltage,fvoltage,steps,delay):
        """
        RAMP1 ramps one channel from an initial voltage to a final voltage within an specified number steps and a delay (microseconds) between steps.
        When the execution finishes, it returns "RAMP_FINISHED".
        """
        dev=self.selectedDevice(c)
        dev.timeout(Value(steps*delay + 5000000,'us')) # 5 more seconds than however long the ramp should take
        yield dev.write("RAMP1,%i,%f,%f,%i,%i\r\n"%(port,ivoltage,fvoltage,steps,delay))
        self.sigRamp1Started([str(port),str(ivoltage),str(fvoltage),str(steps),str(delay)])
        ans = yield dev.read()
        dev.timeout(TIMEOUT) # set timeout back to default
        returnValue(ans)

    @setting(106,port1='i',port2='i',ivoltage1='v',ivoltage2='v',fvoltage1='v',fvoltage2='v',steps='i',delay='i',returns='s')
    def ramp2(self,c,port1,port2,ivoltage1,ivoltage2,fvoltage1,fvoltage2,steps,delay):
        """
        RAMP2 ramps one channel from an initial voltage to a final voltage within an specified number steps and a delay (microseconds) between steps. The # of steps is the total number of steps, not the number of steps per channel.
        When the execution finishes, it returns "RAMP_FINISHED".
        """
        dev=self.selectedDevice(c)
        dev.timeout(Value(steps*delay + 5000000,'us')) # 5 more seconds than however long the ramp should take
        yield dev.write("RAMP2,%i,%i,%f,%f,%f,%f,%i,%i\r\n"%(port1,port2,ivoltage1,ivoltage2,fvoltage1,fvoltage2,steps,delay))
        self.sigRamp2Started([str(port1),str(port2),str(ivoltage1),str(ivoltage2),str(fvoltage1),str(fvoltage2),str(steps),str(delay)])
        ans = yield dev.read()
        dev.timeout(TIMEOUT) # set timeout back to default
        returnValue(ans)

    @setting(107,dacPorts='*i', adcPorts='*i', ivoltages='*v[]', fvoltages='*v[]', steps='i',dacInterval='v[]',dacSettlingTime='v[]',nReadings='i',returns='**v[]')#(*v[],*v[])')
    def dac_led_buffer_ramp(self,c,dacPorts,adcPorts,ivoltages,fvoltages,steps,dacInterval,dacSettlingTime,nReadings=1):
        """
        BUFFER_RAMP ramps the specified output channels from the initial voltages to the final voltages and reads the specified input channels in a synchronized manner.
        It does it within an specified number steps and a delay (dacInterval, microseconds) between the update of the last output channel and the reading of the first input channel.
        """
        dacN = len(dacPorts)
        adcN = len(adcPorts)
        sdacPorts = ""
        sadcPorts = ""
        sivoltages = ""
        sfvoltages = ""
        
        sdacconfig = ""
        sadcconfig = ""


        for x in range(dacN):
            sdacPorts = sdacPorts + str(dacPorts[x])
            sivoltages = sivoltages + str(ivoltages[x]) + ","
            sfvoltages = sfvoltages + str(fvoltages[x]) + ","
            sdacconfig = sdacconfig + f"{dacPorts[x]},{ivoltages[x]},{fvoltages[x]},"

        sivoltages = sivoltages[:-1]
        sfvoltages = sfvoltages[:-1]
        sdacconfig = sdacconfig[:-1]

        for x in range(adcN):
            sadcPorts = sadcPorts + str(adcPorts[x])
            sadcconfig = sadcconfig + str(adcPorts[x]) + ","

        sadcconfig = sadcconfig[:-1]

        dev = self.selectedDevice(c)
        yield dev.write(f"DAC_LED_BUFFER_RAMP,{dacN},{adcN},{steps},{nReadings},{dacInterval},{dacSettlingTime},{sdacconfig},{sadcconfig}\r\n")
        self.sigBufferRampStarted([dacPorts, adcPorts, ivoltages, fvoltages, str(steps), str(dacInterval), str(dacSettlingTime), str(nReadings)])

        channels = []
        data = b''
        
        dev.setramping(True)
        try:
            nbytes = 0
            totalbytes = steps * adcN * 4
            while dev.isramping() and (nbytes < totalbytes):
                bytestoread = yield dev.in_waiting()
                if bytestoread > 0:
                    if nbytes + bytestoread > totalbytes:
                        tmp = yield dev.readByte(totalbytes - nbytes)
                        data = data + tmp
                        nbytes = totalbytes
                    else:
                        tmp = yield dev.readByte(bytestoread)
                        data = data + tmp
                        nbytes = nbytes + bytestoread

                if data.startswith(b'FAILURE'):
                    while not data.endswith(b'\r\n'):
                        bytestoread = yield dev.in_waiting()
                        if bytestoread > 0:
                            tmp = yield dev.readByte(bytestoread)
                            data += tmp

                    raise ValueError(data.decode('utf-8').strip())

            dev.setramping(False)


            for x in range(adcN):
                channels.append([])
            
            for i in range(len(data) // 4):
                voltage = np.frombuffer(data[i * 4:(i + 1) * 4], dtype=np.float32)[0]

                channel_index = i % adcN
                channels[channel_index].append(float(voltage))
            
            # voltages = frombuffer(data, dtype=float32).tolist()

            # for x in range(0, steps * adcN, adcN):
            #     for y in range(adcN):
            #         try:
            #             channels[y].append(voltages[x + y])
            #         except IndexError:
            #             channels[y].append(0)
        
        except KeyboardInterrupt:
            print('Stopped')

        try:
            yield dev.reset_input_buffer()
        except:
            print("Error clearing the serial buffer after buffer_ramp")
        returnValue(channels)
    
    # da.time_series_buffer_ramp_2d([0],[1],[0],[0],[5],[5],[0],10,5,true,500,1000)
    @setting(126,fastDacPorts='*i',slowDacPorts='*i',adcPorts='*i',fastDacV0='*v[]',fastDacVf='*v[]',slowDacV0='*v[]',slowDacVf='*v[]',stepsFast='i',stepsSlow='i',retrace='b',dacPeriod_us='v[]',adcPeriod_us='v[]',returns='***v[]')
    def time_series_buffer_ramp_2d(self,c,fastDacPorts,slowDacPorts,adcPorts,fastDacV0,fastDacVf,slowDacV0,slowDacVf,stepsFast,stepsSlow,retrace, dacPeriod_us,adcPeriod_us):
        slowDacN = len(slowDacPorts)
        fastDacN = len(fastDacPorts)
        adcN = len(adcPorts)
        sadcPorts = ""
        
        sslowDacConfig = ""
        sfastDacConfig = ""
        
        for x in range(slowDacN):
            sslowDacConfig += f"{slowDacPorts[x]},{slowDacV0[x]},{slowDacVf[x]},"
        
        sslowDacConfig = sslowDacConfig[:-1]
        
        for x in range(fastDacN):
            sfastDacConfig += f"{fastDacPorts[x]},{fastDacV0[x]},{fastDacVf[x]},"
        
        sfastDacConfig = sfastDacConfig[:-1]
        
        for x in range(adcN):
            sadcPorts += f"{adcPorts[x]},"
        
        sadcPorts = sadcPorts[:-1]
        
        dev = self.selectedDevice(c)
        yield dev.write(f"2D_TIME_SERIES_BUFFER_RAMP,{fastDacN+slowDacN},{adcN},{stepsFast},{stepsSlow},{dacPeriod_us},{adcPeriod_us},{'1' if retrace else '0'},{fastDacN},{sfastDacConfig},{slowDacN},{sslowDacConfig},{sadcPorts}\r\n")
        
        
        dev.setramping(True)
        try:
            outputData = []
            for _ in range(stepsSlow):
                channels = []
                data = b''
                nbytes = 0
                totalbytes = int(stepsFast * (dacPeriod_us / adcPeriod_us)) * adcN * 4
                while dev.isramping() and (nbytes < totalbytes):
                    bytestoread = yield dev.in_waiting()
                    if bytestoread > 0:
                        if nbytes + bytestoread > totalbytes:
                            tmp = yield dev.readByte(totalbytes - nbytes)
                            data = data + tmp
                            nbytes = totalbytes
                        else:
                            tmp = yield dev.readByte(bytestoread)
                            data = data + tmp
                            nbytes = nbytes + bytestoread
                            
                    if data.startswith(b'FAILURE'):
                        while not data.endswith(b'\r\n'):
                            bytestoread = yield dev.in_waiting()
                            if bytestoread > 0:
                                tmp = yield dev.readByte(bytestoread)
                                data += tmp
                        raise ValueError(data.decode('utf-8').strip())
                
                dev.setramping(False)
                
                for x in range(adcN):
                    channels.append([])

                for i in range(len(data) // 4):
                    voltage = np.frombuffer(data[i * 4:(i + 1) * 4], dtype=np.float32)[0]

                    channel_index = i % adcN
                    channels[channel_index].append(float(voltage)) 
                
                outputData.append(channels)
            
        
        except KeyboardInterrupt:
            print('Stopped')
        
        
        try:
            yield dev.reset_input_buffer()
        except:
            print("Error clearing the serial buffer after buffer_ramp")

        returnValue(outputData)
    
    @setting(127,fastDacPorts='*i',slowDacPorts='*i',adcPorts='*i',fastDacV0='*v[]',fastDacVf='*v[]',slowDacV0='*v[]',slowDacVf='*v[]',stepsFast='i',stepsSlow='i',retrace='b',numAdcAverages='i',dacPeriod_us='v[]',dacSettlingTime_us='v[]',returns='***v[]')
    def dac_led_buffer_ramp_2d(self,c,fastDacPorts,slowDacPorts,adcPorts,fastDacV0,fastDacVf,slowDacV0,slowDacVf,stepsFast,stepsSlow,retrace,numAdcAverages,dacPeriod_us,dacSettlingTime_us):
        slowDacN = len(slowDacPorts)
        fastDacN = len(fastDacPorts)
        adcN = len(adcPorts)
        sadcPorts = ""
        
        sslowDacConfig = ""
        sfastDacConfig = ""
        
        for x in range(slowDacN):
            sslowDacConfig += f"{slowDacPorts[x]},{slowDacV0[x]},{slowDacVf[x]},"
        
        sslowDacConfig = sslowDacConfig[:-1]
        
        for x in range(fastDacN):
            sfastDacConfig += f"{fastDacPorts[x]},{fastDacV0[x]},{fastDacVf[x]},"
        
        sfastDacConfig = sfastDacConfig[:-1]
        
        for x in range(adcN):
            sadcPorts += f"{adcPorts[x]},"
        
        sadcPorts = sadcPorts[:-1]
        
        dev = self.selectedDevice(c)
        yield dev.write(f"2D_DAC_LED_BUFFER_RAMP,{fastDacN+slowDacN},{adcN},{stepsFast},{stepsSlow},{dacPeriod_us},{dacSettlingTime_us},{'1' if retrace else '0'},{numAdcAverages},{fastDacN},{sfastDacConfig},{slowDacN},{sslowDacConfig},{sadcPorts}\r\n")
        
        
        dev.setramping(True)
        try:
            outputData = []
            for _ in range(stepsSlow):
                channels = []
                data = b''
                nbytes = 0
                totalbytes = stepsFast * adcN * 4
                while dev.isramping() and (nbytes < totalbytes):
                    bytestoread = yield dev.in_waiting()
                    if bytestoread > 0:
                        if nbytes + bytestoread > totalbytes:
                            tmp = yield dev.readByte(totalbytes - nbytes)
                            data = data + tmp
                            nbytes = totalbytes
                        else:
                            tmp = yield dev.readByte(bytestoread)
                            data = data + tmp
                            nbytes = nbytes + bytestoread
                    if data.startswith(b'FAILURE'):
                        while not data.endswith(b'\r\n'):
                            bytestoread = yield dev.in_waiting()
                            if bytestoread > 0:
                                tmp = yield dev.readByte(bytestoread)
                                data += tmp

                        raise ValueError(data.decode('utf-8').strip())

                for x in range(adcN):
                    channels.append([])

                for i in range(len(data) // 4):
                    voltage = np.frombuffer(data[i * 4:(i + 1) * 4], dtype=np.float32)[0]

                    channel_index = i % adcN
                    channels[channel_index].append(float(voltage))
                
                outputData.append(channels)
            
            dev.setramping(False)
        
        except KeyboardInterrupt:
            print('Stopped')
        
        
        try:
            yield dev.reset_input_buffer()
        except:
            print("Error clearing the serial buffer after buffer_ramp")

        returnValue(outputData)
    
    @setting(128, dacPorts='*i', adcPorts='*i', ivoltages_1='*v[]', fvoltages_1='*v[]', ivoltages_2='*v[]', fvoltages_2='*v[]', dacsteps='i',numAdcMeasuresPerDacStep='i',numAdcAverages='i', numAdcConversionSkips='i', adcConversionTime_us='i', returns='**v[]')#(*v[],*v[])')
    def boxcar_buffer_ramp_debug(self,c,dacPorts,adcPorts,ivoltages_1,fvoltages_1,ivoltages_2,fvoltages_2,dacsteps,numAdcMeasuresPerDacStep,numAdcAverages,numAdcConversionSkips,adcConversionTime_us):
        """
        """
        dacN = len(dacPorts)
        adcN = len(adcPorts)
        sdacconfig = ""
        sadcconfig = ""

        for x in range(dacN):
            sdacconfig += f"{dacPorts[x]},{ivoltages_1[x]},{fvoltages_1[x]},{ivoltages_2[x]},{fvoltages_2[x]},"

        sdacconfig = sdacconfig[:-1]

        for x in range(adcN):
            sadcconfig += f"{adcPorts[x]},"
        
        sadcconfig = sadcconfig[:-1]

        dev = self.selectedDevice(c)

        yield dev.write(f"BOXCAR_BUFFER_RAMP_DEBUG,{dacN},{adcN},{dacsteps},{numAdcMeasuresPerDacStep},{numAdcAverages},{numAdcConversionSkips},{adcConversionTime_us},{sdacconfig},{sadcconfig}\r\n")
        
        channels = []
        data = b''
        dev.setramping(True)
        try:
            nbytes = 0
            totalbytes = (2 * dacsteps * numAdcAverages + 1) * numAdcMeasuresPerDacStep * adcN * 4
            while dev.isramping() and (nbytes < totalbytes):
                bytestoread = yield dev.in_waiting()
                if bytestoread > 0:
                    if nbytes + bytestoread > totalbytes:
                        tmp = yield dev.readByte(totalbytes - nbytes)
                        data = data + tmp
                        nbytes = totalbytes
                    else:
                        tmp = yield dev.readByte(bytestoread)
                        data = data + tmp
                        nbytes = nbytes + bytestoread
                if data.startswith(b'FAILURE'):
                    while not data.endswith(b'\r\n'):
                        bytestoread = yield dev.in_waiting()
                        if bytestoread > 0:
                            tmp = yield dev.readByte(bytestoread)
                            data += tmp
                    raise ValueError(data.decode('utf-8').strip())
            dev.setramping(False)

            for x in range(adcN):
                channels.append([])

            for i in range(len(data) // 4):
                voltage = np.frombuffer(data[i * 4:(i + 1) * 4], dtype=np.float32)[0]

                channel_index = i % adcN
                channels[channel_index].append(float(voltage))

        except KeyboardInterrupt:
            print('Stopped')

        #Reads BUFFER_RAMP_FINISHED
        try:
            yield dev.reset_input_buffer()
        except:
            print("Error clearing the serial buffer after buffer_ramp")

        returnValue(channels)
    
    @setting(129, dacPorts='*i', adcPorts='*i', ivoltages_1='*v[]', fvoltages_1='*v[]', ivoltages_2='*v[]', fvoltages_2='*v[]', dacsteps='i',numAdcMeasuresPerDacStep='i',numAdcAverages='i', numAdcConversionSkips='i', adcConversionTime_us='i', returns='**v[]')#(*v[],*v[])')
    def boxcar_buffer_ramp_window_average(self,c,dacPorts,adcPorts,ivoltages_1,fvoltages_1,ivoltages_2,fvoltages_2,dacsteps,numAdcMeasuresPerDacStep,numAdcAverages,numAdcConversionSkips,adcConversionTime_us):
        """
        """
        rawData = yield self.boxcar_buffer_ramp_debug(c,dacPorts,adcPorts,ivoltages_1,fvoltages_1,ivoltages_2,fvoltages_2,dacsteps,numAdcMeasuresPerDacStep,numAdcAverages,numAdcConversionSkips,adcConversionTime_us)
        output = []
        for adcIndex in range(len(adcPorts)):
            data=rawData[adcIndex]
            adcOutput = []
            data_length = len(data)
            for i in range(data_length):
                period_index = i // (numAdcMeasuresPerDacStep*2)
                position_in_period = i % (numAdcMeasuresPerDacStep*2)
                
                values =[]
                for p in range(numAdcAverages):
                    curr_period = period_index + p
                    idx = curr_period * (numAdcMeasuresPerDacStep*2) + position_in_period
                    if idx < data_length:
                        values.append(data[idx])
                    else:
                        break
                if len(values) > 0:
                    avg = np.mean(values)
                    adcOutput.append(avg)
                else:
                    adcOutput.append(data[i])
            output.append(adcOutput)
        returnValue(output)

    @setting(108,dacPorts='*i', adcPorts='*i', ivoltages='*v[]', fvoltages='*v[]', steps='i',dacPeriod_us='v[]',adcPeriod_us='v[]',returns='**v[]')#(*v[],*v[])')
    def time_series_buffer_ramp(self,c,dacPorts,adcPorts,ivoltages,fvoltages,steps,dacPeriod_us,adcPeriod_us):
        """
        TIME_SERIES_BUFFER_RAMP ramps the specified output channels from the initial voltages to the final voltages and reads the specified input channels in a synchronized manner.
        It does it within an specified number steps, with DAC voltages being updated every dacPeriod_us and ADC voltages read every adcPeriod_us
        """

        dacN = len(dacPorts)
        adcN = len(adcPorts)
        sdacPorts = ""
        sadcPorts = ""
        sivoltages = ""
        sfvoltages = ""
        sdacconfig = ""
        sadcconfig = ""

        for x in range(dacN):
            sdacPorts = sdacPorts + str(dacPorts[x])
            sivoltages = sivoltages + str(ivoltages[x]) + ","
            sfvoltages = sfvoltages + str(fvoltages[x]) + ","
            sdacconfig += f"{dacPorts[x]},{ivoltages[x]},{fvoltages[x]},"

        sivoltages = sivoltages[:-1]
        sfvoltages = sfvoltages[:-1]
        sdacconfig =sdacconfig[:-1]

        for x in range(adcN):
            sadcPorts = sadcPorts + str(adcPorts[x])
            sadcconfig += f"{adcPorts[x]},"
        
        sadcconfig =sadcconfig[:-1]

        dev = self.selectedDevice(c)
        yield dev.write(f"TIME_SERIES_BUFFER_RAMP,{dacN},{adcN},{steps},{dacPeriod_us},{adcPeriod_us},{sdacconfig},{sadcconfig}\r\n")
        
        channels = []
        data = b''
        dev.setramping(True)
        try:
            nbytes = 0
            totalbytes = int(steps * (dacPeriod_us / adcPeriod_us)) * adcN * 4
            while dev.isramping() and (nbytes < totalbytes):
                bytestoread = yield dev.in_waiting()
                if bytestoread > 0:
                    if nbytes + bytestoread > totalbytes:
                        tmp = yield dev.readByte(totalbytes - nbytes)
                        data = data + tmp
                        nbytes = totalbytes
                    else:
                        tmp = yield dev.readByte(bytestoread)
                        data = data + tmp
                        nbytes = nbytes + bytestoread
                if data.startswith(b'FAILURE'):
                    while not data.endswith(b'\r\n'):
                        bytestoread = yield dev.in_waiting()
                        if bytestoread > 0:
                            tmp = yield dev.readByte(bytestoread)
                            data += tmp
                    raise ValueError(data.decode('utf-8').strip())

            dev.setramping(False)

            for x in range(adcN):
                channels.append([])

            for i in range(len(data) // 4):
                voltage = np.frombuffer(data[i * 4:(i + 1) * 4], dtype=np.float32)[0]

                channel_index = i % adcN
                channels[channel_index].append(float(voltage))

        except KeyboardInterrupt:
            print('Stopped')

        #Reads BUFFER_RAMP_FINISHED
        try:
            yield dev.reset_input_buffer()
        except:
            print("Error clearing the serial buffer after buffer_ramp")

        returnValue(channels)

    @setting(109,channel='i',time='v[]',returns='v[]')
    def set_conversionTime(self,c,channel,time):
        """
        CONVERT_TIME sets the conversion time for the ADC. The conversion time is the time the ADC takes to convert the analog signal to a digital signal.
        Keep in mind that the smaller the conversion time, the more noise your measurements will have. Maximum conversion time: 2686 microseconds. Minimum conversion time: 82 microseconds.
        """
        if not (channel in self.channels):
            returnValue("Error: invalid channel. Must be in 0,1,2,3")
        if not (82 <= time <= 2686):
            returnValue("Error: invalid conversion time. Must adhere to (82 <= t <= 2686) (t is in microseconds)")
        dev=self.selectedDevice(c)
        yield dev.write("CONVERT_TIME,%i,%f\r\n"%(channel,time))
        ans = yield dev.read()
        self.sigConvTimeSet([str(channel),str(ans)])
        returnValue(float(ans))


    @setting(110,returns='s')
    def id(self,c):
        """
        IDN? returns the string.
        """
        dev=self.selectedDevice(c)
        yield dev.write("*IDN?\r\n")
        time.sleep(1)
        ans = yield dev.read()
        returnValue(ans)

    @setting(111,returns='s')
    def ready(self,c):
        """
        RDY? returns the string "READY" when the DAC-ADC is ready for a new operation.
        """
        dev=self.selectedDevice(c)
        yield dev.write("*RDY?\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(112, returns='w')
    def in_waiting(self, c):
        """
        Return number of bytes in the input buffer.
        """
        dev = self.selectedDevice(c)
        ans = yield dev.in_waiting()
        returnValue(ans)

    @setting(113)
    def stop_ramp(self,c):
        """
        Stops buffer_ramp and dis_buffer_ramp only.
        Discards all elements from input buffer.
        """
        dev=self.selectedDevice(c)
        yield dev.write("STOP\r\n")
        dev.setramping(False)

        #Let ramps finish up
        yield self.sleep(0.25)

        #Read remaining bytes if somehow some are left over
        bytestoread = yield dev.in_waiting()
        if bytestoread >0:
            yield dev.readByte(bytestoread)

    @setting(114,returns='s')
    def dac_ch_calibration(self,c):
        """
        Calibrates each DAC channel.
        Connect each DAC to each ADC channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write("DAC_CH_CAL\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(115,returns='s')
    def adc_zero_sc_calibration(self,c):
        """
        Calibrates each DAC channel.
        Connect each DAC to each ADC channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write("ADC_ZERO_SC_CAL\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(116,returns='s')
    def adc_ch_zero_sc_calibration(self,c):
        """
        Calibrates ADC Zero scale for each channel.
        Connect a zero scale voltage to each channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write("ADC_CH_ZERO_SC_CAL\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(117,returns='s')
    def adc_ch_full_sc_calibration(self,c):
        """
        Calibrates ADC Full scale for each channel.
        Connect a full scale voltage to each channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write("ADC_CH_FULL_SC_CAL\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(118,returns='s')
    def initialize(self,c):
        """
        Initializes DACs
        """
        dev=self.selectedDevice(c)
        yield dev.write("INITIALIZE\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(119,unit='i',returns='s')
    def delay_unit(self,c,unit):
        """
        Sets delay unit. 0 = microseconds(default) 1 = miliseconds
        """
        dev=self.selectedDevice(c)
        yield dev.write("SET_DUNIT,%i\r\n"%(unit))
        ans = yield dev.read()
        returnValue(ans)

    @setting(120,voltage='v',returns='s')
    def dac_full_scale(self,c,voltage):
        """
        Sets the dac full scale.
        """
        dev=self.selectedDevice(c)
        yield dev.write("FULL_SCALE,%f\r\n"%(voltage))
        ans = yield dev.read()
        returnValue(ans)

    @setting(121)
    def set_offset_and_gain(self,c,offset_and_gain):
        """
        Set the offset and gain for all DAC channels.
        """
        dev=self.selectedDevice(c)
        message = "SET_OSG" + ",%f"*8 + "\r\n"
        yield dev.write(message%(tuple(offset_and_gain)))
        ans = [0]*8
        for i in range(8):
            ans[i] = yield dev.read()

        returnValue(ans)

    @setting(122)
    def inquiry_offset_and_gain(self,c):
        """
        Print the current offset and gain values for all DAC channels.
        """
        dev=self.selectedDevice(c)
        yield dev.write("INQUIRY_OSG\r\n")
        ans = [0]*8
        for i in range(8):
            ans[i] = yield dev.read()

        returnValue(ans)


    @setting(123)
    def sn(self,c):
        """
        Returns the serial number of the box.
        """
        dev = self.selectedDevice(c)
        yield dev.write("SERIAL_NUMBER\r\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(124,channel='i',code='i')
    def set_dac_code(self,c,channel,code):
        """
        SET_DAC_CODE writes a code between 0 and 1048576 to a channel and returns the channel and the code written to that DAC's register.
        """
        if not (channel in range(4)):
            returnValue("Error: invalid port number.")
            return
        if (code > 1048576) or (code < 0):
            returnValue("Error: invalid code. Must be between 0 and 1048576.")
            return
        dev=self.selectedDevice(c)
        yield dev.write("SET_DAC_CODE,%i,%i\r\n"%(channel,code))
        ans = yield dev.read()
        code = ans.lower().partition(' to ')[2][:-1]
        self.sigOutputSet([str(channel),code])
        returnValue(ans)

    @setting(125,channel='i')
    def read_dac_voltage(self,c,channel):
        """
        GET_DAC returns the most recent value to which the provided channel was set.
        """
        if not (channel in range(4)):
            returnValue("Error: invalid port number.")
        dev = self.selectedDevice(c)
        yield dev.write("GET_DAC,%i\r\n"%(channel))
        ans = yield dev.read()
        returnValue(float(ans))

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

    @setting(9005,time='v[s]')
    def timeout(self,c,time):
        dev=self.selectedDevice(c)
        yield dev.timeout(time)

    @setting(9100)
    def send_read_requests(self,c):
        dev = self.selectedDevice(c)
        for port in [0,1,2,3]:
            yield dev.write("GET_ADC,%i\r\n"%port)
            ans = yield dev.read()
            self.sigInputRead([str(port),str(ans)])

    def sleep(self,secs):
        """Asynchronous compatible sleep command. Sleeps for given time in seconds, but allows
        other operations to be done elsewhere while paused."""
        d = defer.Deferred()
        reactor.callLater(secs,d.callback,'Sleeping')
        return d

    # GET_DAC hasn't been added to the DAC ADC code yet
    # @setting(9101)
    # def send_get_dac_requests(self,c):
    #     yield


__server__ = DAC_ADCServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
