# Copyright UCSB AFY Lab
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
from labrad.wrappers import connectAsync
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor, defer
# import labrad.units as units
from labrad.types import Value
import json
import numpy as np
import time
from pathlib import Path
from datetime import datetime

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
    name = 'DAC-ADC-GIGA'
    deviceName = 'Arduino DAC-ADC-GIGA'
    deviceWrapper = DAC_ADCWrapper

    channels = [0,1,2,3]

    sPrefix = 703000
    sigInputRead         = Signal(sPrefix+0,'signal__input_read'         , '*s') #
    sigOutputSet         = Signal(sPrefix+1,'signal__output_set'         , '*s') #
    sigRamp1Started      = Signal(sPrefix+2,'signal__ramp_1_started'     , '*s') #
    sigRamp2Started      = Signal(sPrefix+3,'signal__ramp_2_started'     , '*s') #
    sigConvTimeSet       = Signal(sPrefix+4,'signal__conversion_time_set', '*s') #
    sigBufferRampStarted = Signal(sPrefix+5,'signal__buffer_ramp_started', '*s') #
    sigSpectrumStarted = Signal(sPrefix+6, 'signal__spectrum_started','*s') #
    sig2DRampLine = Signal(sPrefix+7, 'signal__2d_ramp_line', '*s') #
    sigAWGData = Signal(sPrefix+8, 'signal__awg_data', '*s') #

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
        yield reg.cd(['', 'Servers', 'dac_adc_giga', 'Links'], True)
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
        if not (port in range(8)):
            returnValue("Error: invalid port number.")
            return
        if (voltage > 10) or (voltage < -10):
            returnValue("Error: invalid voltage. It must be between -10 and 10.")
            return
        dev=self.selectedDevice(c)
        yield dev.write("SET,%i,%f\n"%(port,voltage))
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
        yield dev.write("GET_ADC,%i\n"%port)
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
        yield dev.write("RAMP1,%i,%f,%f,%i,%i\n"%(port,ivoltage,fvoltage,steps,delay))
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
        yield dev.write("RAMP2,%i,%i,%f,%f,%f,%f,%i,%i\n"%(port1,port2,ivoltage1,ivoltage2,fvoltage1,fvoltage2,steps,delay))
        self.sigRamp2Started([str(port1),str(port2),str(ivoltage1),str(ivoltage2),str(fvoltage1),str(fvoltage2),str(steps),str(delay)])
        ans = yield dev.read()
        dev.timeout(TIMEOUT) # set timeout back to default
        returnValue(ans)

    @setting(131,dacPorts='*i', adcPorts='*i', ivoltages='*v[]', fvoltages='*v[]', steps='i',delay='v[]',nReadings='i',returns='**v[]')#(*v[],*v[])')
    def buffer_ramp(self,c,dacPorts,adcPorts,ivoltages,fvoltages,steps,delay,nReadings=1):
        
        
        # first, see if settlingTime is allowed
        # check to see if buffer ramp is compatible with the current ADC configuration
        convTimeSum = [0.0, 0.0, 0.0, 0.0]
        numAdcChannels = len(adcPorts)
        numAdcAverages = nReadings if nReadings is not None else 1

        for i in range(numAdcChannels):
            chNum = adcPorts[i]
            board_num = chNum // 4
            conv_time = yield self.get_conversion_time(c, chNum)
            convTimeSum[board_num] += conv_time

        maxConvTime = max(convTimeSum)
        maxConvTimeTotal = maxConvTime * numAdcAverages
        
        

        dac_settling_time_us = int(delay*0.8 + 0.5) # default settling time
        dac_interval_us = delay
        
        
        if maxConvTimeTotal + dac_settling_time_us + 180 >= dac_interval_us:
            dac_settling_time_us = dac_interval_us - maxConvTimeTotal - 181
            dac_settling_time_us = max(dac_settling_time_us, 100)
            # print(f"DAC settling time is too long for specified ADC conversion time, minimized settling time to {dac_settling_time_us}us")
        
        
        if maxConvTimeTotal + dac_settling_time_us + 180 >= dac_interval_us:
            dac_interval_us = maxConvTimeTotal + dac_settling_time_us + 181
            print(f"DAC interval is too short for specified ADC conversion time, made delay {dac_interval_us}us")
        
        
        
        out = yield self.dac_led_buffer_ramp(c, dacPorts, adcPorts, ivoltages, fvoltages, steps, dac_interval_us, dac_settling_time_us, nReadings=nReadings)
        returnValue(out)

    @setting(132,dacPorts='*i', adcPorts='*i', ivoltages='*v[]', fvoltages='*v[]', steps='i',delay='v[]',nReadings='i',adcSteps='i',returns='**v[]')#(*v[],*v[])')
    def buffer_ramp_dis(self,c,dacPorts,adcPorts,ivoltages,fvoltages,steps,delay,adcSteps,nReadings=1):
       out = yield self.time_series_buffer_ramp(c, dacPorts, adcPorts, ivoltages, fvoltages, steps, delay, steps*delay/adcSteps )
       returnValue(out)


    @setting(107,dacPorts='*i', adcPorts='*i', ivoltages='*v[]', fvoltages='*v[]', steps='i',dacInterval='v[]',dacSettlingTime='v[]',nReadings='i',returns='**v[]')#(*v[],*v[])')
    def dac_led_buffer_ramp(self,c,dacPorts,adcPorts,ivoltages,fvoltages,steps,dacInterval,dacSettlingTime,nReadings=1):
        """
        BUFFER_RAMP ramps the specified output channels from the initial voltages to the final voltages and reads the specified input channels in a synchronized manner.
        It does it within an specified number steps and a delay (dacInterval, microseconds) between the update of the last output channel and the reading of the first input channel.
        """
        dacN = len(dacPorts)
        adcN = len(adcPorts)

        dev = self.selectedDevice(c)
        command_parts = [
            "DAC_LED_BUFFER_RAMP",
            str(dacN),
            str(adcN),
            str(steps),
            str(nReadings),
            str(dacInterval),
            str(dacSettlingTime),
            *[str(ch) for ch in dacPorts],
            *[str(v) for v in ivoltages],
            *[str(v) for v in fvoltages],
            *[str(ch) for ch in adcPorts],
        ]
        yield dev.write(",".join(command_parts) + "\n")
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
                    while not data.endswith(b'\n'):
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

        extraBytes = b''
        bytestoread = yield dev.in_waiting()

        if bytestoread > 0:
            while not extraBytes.endswith(b'\n'):
                bytestoread = yield dev.in_waiting()
                if bytestoread > 0:
                    tmp = yield dev.readByte(bytestoread)
                    extraBytes += tmp

        try:
            decoded = extraBytes.decode('utf-8').strip()
            if decoded.startswith('FAILURE'):
                print(decoded)
        except UnicodeDecodeError as e:
            print(f"Decode error at byte {e.start}: {e.reason}")
            print(f"Raw data: {extraBytes}")

        
        try:
            yield dev.reset_input_buffer()
        except:
            print("Error clearing the serial buffer after buffer_ramp")
        returnValue(channels)

    # @setting(107,dacPorts='*i', adcPorts='*i', ivoltages='*v[]', fvoltages='*v[]', steps='i',dacInterval='v[]',dacSettlingTime='v[]',nReadings='i',returns='**v[]')#(*v[],*v[])')
    @setting(221,dacPorts='*i', voltageLists='**v[]',dacInterval='i',returns='**v[]')
    def generate_awg(self,c,dacPorts,voltageLists,dacInterval):
        """
        BUFFER_RAMP ramps the specified output channels from the initial voltages to the final voltages and reads the specified input channels in a synchronized manner.
        It does it within an specified number steps and a delay (dacInterval, microseconds) between the update of the last output channel and the reading of the first input channel.
        """
        dacN = len(dacPorts)
        numDacStepsPerLoop = len(voltageLists[0]) if voltageLists else 0
        
        dev = self.selectedDevice(c)
        
        command_parts = [
            "AWG_BUFFER_RAMP",
            str(dacN),
            str(numDacStepsPerLoop),
            str(dacInterval),
            *[str(ch) for ch in dacPorts],
            *[str(v) for channel in voltageLists for v in channel],
        ]
        command = ",".join(command_parts) + "\n"
        print(command)
        yield dev.write(command)
        
        self.sigBufferRampStarted([dacPorts, [], voltageLists, str(0), str(numDacStepsPerLoop), str(dacInterval), str(0), str(0)])

        channels = []
        data = b''
        
        dev.setramping(True)

        try:
            yield dev.reset_input_buffer()
        except:
            print("Error clearing the serial buffer after buffer_ramp")
        returnValue(channels)

    @setting(222, dacPorts='*i', adcPorts='*i', voltageLists='**v[]', dacInterval_us='i', numCycles='i', returns='**v[]')
    def awg_with_adc(self, c, dacPorts, adcPorts, voltageLists, dacInterval_us, numCycles=1):
        """Run precomputed DAC waveform while reading ADC. numCycles=0 runs forever until STOP."""
        dacPorts = [int(ch) for ch in dacPorts]
        adcPorts = [int(ch) for ch in adcPorts]
        dacN = len(dacPorts)
        adcN = len(adcPorts)
        numSteps = len(voltageLists[0]) if voltageLists else 0

        if numSteps < 1:
            raise ValueError("voltageLists must have at least one step")

        # Get conversion time to estimate expected ADC readings
        conv_time_us = 500.0  # default
        if adcPorts:
            conv_time_us = yield self.get_conversion_time(c, adcPorts[0])

        command_parts = [
            "AWG_WITH_ADC",
            str(dacN),
            str(adcN),
            str(numSteps),
            str(dacInterval_us),
            str(numCycles),
            *[str(ch) for ch in dacPorts],
            *[str(ch) for ch in adcPorts],
            *[str(v) for channel in voltageLists for v in channel],
        ]

        dev = self.selectedDevice(c)
        yield dev.write(",".join(command_parts) + "\n")

        channels = [[] for _ in range(adcN)]
        data = b''
        dev.setramping(True)

        # Calculate expected ADC readings based on timing (0 = run forever)
        run_forever = (numCycles == 0)
        if run_forever:
            totalbytes = float('inf')
        else:
            total_dac_time_us = numSteps * numCycles * dacInterval_us
            expected_adc_readings = int(total_dac_time_us // conv_time_us)
            totalbytes = expected_adc_readings * adcN * 4

        batch_count = 0

        try:
            nbytes = 0
            while dev.isramping() and (nbytes < totalbytes):
                bytestoread = yield dev.in_waiting()
                if bytestoread > 0:
                    if not run_forever and nbytes + bytestoread > totalbytes:
                        tmp = yield dev.readByte(int(totalbytes) - nbytes)
                        data = data + tmp
                        nbytes = int(totalbytes)
                    else:
                        tmp = yield dev.readByte(bytestoread)
                        data = data + tmp
                        nbytes = nbytes + bytestoread

                    # Parse and emit any complete readings
                    complete_readings = len(data) // (adcN * 4)
                    while batch_count < complete_readings:
                        batch_start = batch_count * adcN * 4
                        batch_data = data[batch_start:batch_start + adcN * 4]

                        reading_values = []
                        for i in range(adcN):
                            voltage = np.frombuffer(batch_data[i * 4:(i + 1) * 4], dtype=np.float32)[0]
                            channels[i].append(float(voltage))
                            reading_values.append(float(voltage))

                        # Emit signal with this batch
                        payload = json.dumps({
                            "reading_index": batch_count,
                            "adc_ports": adcPorts,
                            "values": reading_values,
                        })
                        self.sigAWGData([payload])
                        batch_count += 1

                if data.startswith(b'FAILURE'):
                    while not data.endswith(b'\n'):
                        bytestoread = yield dev.in_waiting()
                        if bytestoread > 0:
                            tmp = yield dev.readByte(bytestoread)
                            data += tmp
                    raise ValueError(data.decode('utf-8').strip())

            dev.setramping(False)

        except KeyboardInterrupt:
            print('AWG stopped by user')

        # Send STOP command to firmware
        yield dev.write("STOP\n")
        yield self.sleep(0.1)

        # Drain any remaining bytes
        try:
            yield dev.reset_input_buffer()
        except:
            print("Error clearing serial buffer after AWG")

        returnValue(channels)

    @setting(126, dacPorts='*i', adcPorts='*i', startPoint='*v[]', fastAxisVector='*v[]', slowAxisVector='*v[]', stepsFast='i', stepsSlow='i', retrace='b', snake='b', dacInterval_us='v[]', adcInterval_us='v[]', returns='**v[]')
    def time_series_buffer_ramp_2d(self, c, dacPorts, adcPorts, startPoint, fastAxisVector, slowAxisVector, stepsFast, stepsSlow, retrace, snake, dacInterval_us, adcInterval_us):
        """
        TIME_SERIES_BUFFER_RAMP_2D sweeps an arbitrary 2D plane within the DAC
        phase space. The plane is defined by a common `startPoint` plus two
        spanning vectors (`fastAxisVector`, `slowAxisVector`). For every slow
        step the fast axis is traversed `stepsFast` times, with DAC updates
        occurring every `dacInterval_us` and ADC captures every `adcInterval_us`.

        Args:
            dacPorts: Sequence of DAC channel IDs participating in the sweep.
            adcPorts: Sequence of ADC channel IDs to digitize.
            startPoint: Absolute DAC coordinates at the origin of the plane.
            fastAxisVector: Vector added as the fast parameter runs from 0→1.
            slowAxisVector: Vector added as the slow parameter runs from 0→1.
            stepsFast: Number of DAC points sampled along the fast parameter.
            stepsSlow: Number of slow parameter points.
            retrace: If true, perform backward traces for each slow step.
            snake: If true, alternate fast direction between slow steps.
            dacInterval_us: Time between DAC updates.
            adcInterval_us: Time between ADC acquisitions.

        Emits:
            sig2DRampLine payloads with the following keys:
              - `line_index`: Absolute line counter.
              - `slow_param`: Normalized slow parameter value [0, 1].
              - `fast_direction`: 'forward' or 'backward' traversal of fast axis.
              - `slow_position`/`slow_voltages`: DAC coordinates at fast param 0.
              - `start_point`, `fast_axis_vector`, `slow_axis_vector`: Defining geometry.
              - `dac_ports`, `adc_ports`: Channel metadata.
              - `channels`: ADC samples decoded per channel for the line.
        """
        dacPorts = [int(ch) for ch in dacPorts]
        adcPorts = [int(ch) for ch in adcPorts]
        start_point = [float(v) for v in startPoint]
        fast_axis = [float(v) for v in fastAxisVector]
        slow_axis = [float(v) for v in slowAxisVector]

        dacN = len(dacPorts)
        adcN = len(adcPorts)

        if not (len(start_point) == len(fast_axis) == len(slow_axis) == dacN):
            raise ValueError("startPoint, fastAxisVector, and slowAxisVector must each have one entry per DAC channel")

        if stepsFast <= 0 or stepsSlow <= 0:
            raise ValueError("stepsFast and stepsSlow must be positive integers")

        dac_interval = float(dacInterval_us)
        adc_interval = float(adcInterval_us)

        dev = self.selectedDevice(c)
        retrace_flag = "1.0" if retrace else "0.0"
        snake_flag = "1.0" if snake else "0.0"
        command_parts = [
            "2D_TIME_SERIES_BUFFER_RAMP",
            str(dacN),
            str(adcN),
            str(stepsFast),
            str(stepsSlow),
            f"{dac_interval}",
            f"{adc_interval}",
            retrace_flag,
            snake_flag,
            *[str(ch) for ch in dacPorts],
            *[str(v) for v in start_point],
            *[str(v) for v in fast_axis],
            *[str(v) for v in slow_axis],
            *[str(ch) for ch in adcPorts],
        ]
        yield dev.write(",".join(command_parts) + "\n")
        channels = []
        data = b''
        dev.setramping(True)
        
        # Calculate bytes per line
        points_per_line = max(1, int(stepsFast * dac_interval / adc_interval))
        bytes_per_line = points_per_line * adcN * 4
        total_lines = stepsSlow * (2 if retrace and not snake else 1)
        current_line = 0
        slow_denominator = (stepsSlow - 1) if stepsSlow > 1 else 1
        
        try:
            nbytes = 0
            totalbytes = total_lines * bytes_per_line
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
                
                # Check if we have complete line(s) to emit
                while len(data) >= (current_line + 1) * bytes_per_line:
                    line_start = current_line * bytes_per_line
                    line_end = (current_line + 1) * bytes_per_line
                    line_data = data[line_start:line_end]
                    
                    # Decode this line's data
                    line_channels = [[] for _ in range(adcN)]
                    for i in range(len(line_data) // 4):
                        voltage = np.frombuffer(line_data[i * 4:(i + 1) * 4], dtype=np.float32)[0]
                        channel_index = i % adcN
                        line_channels[channel_index].append(float(voltage))
                    
                    # Calculate slow axis voltage(s) and direction
                    if retrace and not snake:
                        slow_step = current_line // 2
                        is_forward = (current_line % 2) == 0
                    else:
                        slow_step = current_line
                        if snake:
                            is_forward = (slow_step % 2) == 0
                        else:
                            is_forward = True

                    slow_param = float(slow_step) / slow_denominator if slow_denominator else 0.0
                    slow_position = [
                        start_point[j] + slow_param * slow_axis[j]
                        for j in range(dacN)
                    ]
                    direction = 'forward' if is_forward else 'backward'
                    
                    # Emit signal for this line
                    payload = json.dumps({
                        "line_index": current_line,
                        "slow_param": slow_param,
                        "fast_direction": direction,
                        "slow_position": slow_position,
                        "slow_voltages": slow_position,
                        "start_point": start_point,
                        "fast_axis_vector": fast_axis,
                        "slow_axis_vector": slow_axis,
                        "direction": direction,
                        "dac_ports": dacPorts,
                        "channels": line_channels,
                        "adc_ports": adcPorts,
                    })
                    self.sig2DRampLine([payload])
                    
                    current_line += 1
                
                if data.startswith(b'FAILURE'):
                    while not data.endswith(b'\n'):
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

        extraBytes = b''
        bytestoread = yield dev.in_waiting()

        if bytestoread > 0:
            while not extraBytes.endswith(b'\n'):
                bytestoread = yield dev.in_waiting()
                if bytestoread > 0:
                    tmp = yield dev.readByte(bytestoread)
                    extraBytes += tmp

        try:
            decoded = extraBytes.decode('utf-8').strip()
            if decoded.startswith('FAILURE'):
                print(decoded)
        except UnicodeDecodeError as e:
            print(f"Decode error at byte {e.start}: {e.reason}")
            print(f"Raw data: {extraBytes}")


        try:
            yield dev.reset_input_buffer()
        except:
            print("Error clearing the serial buffer after buffer_ramp")

        returnValue(channels)
    
    @setting(127, dacPorts='*i', adcPorts='*i', startPoint='*v[]', fastAxisVector='*v[]', slowAxisVector='*v[]', stepsFast='i', stepsSlow='i', retrace='b', snake='b', numAdcAverages='i', dacInterval_us='v[]', dacSettlingTime_us='v[]', returns='**v[]')
    def dac_led_buffer_ramp_2d(self, c, dacPorts, adcPorts, startPoint, fastAxisVector, slowAxisVector, stepsFast, stepsSlow, retrace, snake, numAdcAverages, dacInterval_us, dacSettlingTime_us):
        """
        DAC_LED_BUFFER_RAMP_2D performs averaged LED-style measurements while
        sweeping an arbitrary planar slice of the DAC phase space. The slice is
        described by a `startPoint` and two spanning vectors
        (`fastAxisVector`, `slowAxisVector`), with DAC updates occurring every
        `dacInterval_us` and enforced settling of `dacSettlingTime_us`.

        Args mirror those of `time_series_buffer_ramp_2d`, with `numAdcAverages`
        specifying the per-point averaging budget prior to emitting a line.

        Emits:
            sig2DRampLine payloads with the same metadata additions as
            `time_series_buffer_ramp_2d`, enabling downstream consumers to
            reconstruct the active 2D slice.
        """
        dacPorts = [int(ch) for ch in dacPorts]
        adcPorts = [int(ch) for ch in adcPorts]
        start_point = [float(v) for v in startPoint]
        fast_axis = [float(v) for v in fastAxisVector]
        slow_axis = [float(v) for v in slowAxisVector]

        dacN = len(dacPorts)
        adcN = len(adcPorts)

        if not (len(start_point) == len(fast_axis) == len(slow_axis) == dacN):
            raise ValueError("startPoint, fastAxisVector, and slowAxisVector must each have one entry per DAC channel")

        if stepsFast <= 0 or stepsSlow <= 0:
            raise ValueError("stepsFast and stepsSlow must be positive integers")

        if numAdcAverages <= 0:
            raise ValueError("numAdcAverages must be a positive integer")

        dac_interval = float(dacInterval_us)
        dac_settling = float(dacSettlingTime_us)

        dev = self.selectedDevice(c)
        retrace_flag = "1.0" if retrace else "0.0"
        snake_flag = "1.0" if snake else "0.0"
        command_parts = [
            "2D_DAC_LED_BUFFER_RAMP",
            str(dacN),
            str(adcN),
            str(stepsFast),
            str(stepsSlow),
            f"{dac_interval}",
            f"{dac_settling}",
            retrace_flag,
            snake_flag,
            str(int(numAdcAverages)),
            *[str(ch) for ch in dacPorts],
            *[str(v) for v in start_point],
            *[str(v) for v in fast_axis],
            *[str(v) for v in slow_axis],
            *[str(ch) for ch in adcPorts],
        ]
        yield dev.write(",".join(command_parts) + "\n")
        channels = []
        data = b''
        dev.setramping(True)
        
        # Calculate bytes per line
        bytes_per_line = stepsFast * adcN * 4
        total_lines = stepsSlow * (2 if retrace and not snake else 1)
        current_line = 0
        slow_denominator = (stepsSlow - 1) if stepsSlow > 1 else 1
        
        try:
            nbytes = 0
            totalbytes = total_lines * bytes_per_line
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
                
                # Check if we have complete line(s) to emit
                while len(data) >= (current_line + 1) * bytes_per_line:
                    line_start = current_line * bytes_per_line
                    line_end = (current_line + 1) * bytes_per_line
                    line_data = data[line_start:line_end]
                    
                    # Decode this line's data
                    line_channels = [[] for _ in range(adcN)]
                    for i in range(len(line_data) // 4):
                        voltage = np.frombuffer(line_data[i * 4:(i + 1) * 4], dtype=np.float32)[0]
                        channel_index = i % adcN
                        line_channels[channel_index].append(float(voltage))
                    
                    # Calculate slow axis voltage(s) and direction
                    if retrace and not snake:
                        slow_step = current_line // 2
                        is_forward = (current_line % 2) == 0
                    else:
                        slow_step = current_line
                        if snake:
                            is_forward = (slow_step % 2) == 0
                        else:
                            is_forward = True

                    slow_param = float(slow_step) / slow_denominator if slow_denominator else 0.0
                    slow_position = [
                        start_point[j] + slow_param * slow_axis[j]
                        for j in range(dacN)
                    ]
                    direction = 'forward' if is_forward else 'backward'
                    
                    # Emit signal for this line
                    payload = json.dumps({
                        "line_index": current_line,
                        "slow_param": slow_param,
                        "fast_direction": direction,
                        "slow_position": slow_position,
                        "slow_voltages": slow_position,
                        "start_point": start_point,
                        "fast_axis_vector": fast_axis,
                        "slow_axis_vector": slow_axis,
                        "direction": direction,
                        "dac_ports": dacPorts,
                        "channels": line_channels,
                        "adc_ports": adcPorts,
                    })
                    self.sig2DRampLine([payload])
                    
                    current_line += 1
                
                if data.startswith(b'FAILURE'):
                    while not data.endswith(b'\n'):
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

        extraBytes = b''
        bytestoread = yield dev.in_waiting()

        if bytestoread > 0:
            while not extraBytes.endswith(b'\n'):
                bytestoread = yield dev.in_waiting()
                if bytestoread > 0:
                    tmp = yield dev.readByte(bytestoread)
                    extraBytes += tmp

        try:
            decoded = extraBytes.decode('utf-8').strip()
            if decoded.startswith('FAILURE'):
                print(decoded)
        except UnicodeDecodeError as e:
            print(f"Decode error at byte {e.start}: {e.reason}")
            print(f"Raw data: {extraBytes}")


        try:
            yield dev.reset_input_buffer()
        except:
            print("Error clearing the serial buffer after buffer_ramp")

        returnValue(channels)
    
    '''
    @setting(128, dacPorts='*i', adcPorts='*i', ivoltages_1='*v[]', fvoltages_1='*v[]', ivoltages_2='*v[]', fvoltages_2='*v[]', dacsteps='i',numAdcMeasuresPerDacStep='i',numAdcAverages='i', numAdcConversionSkips='i', adcConversionTime_us='i', returns='**v[]')#(*v[],*v[])')
    def boxcar_buffer_ramp_debug(self,c,dacPorts,adcPorts,ivoltages_1,fvoltages_1,ivoltages_2,fvoltages_2,dacsteps,numAdcMeasuresPerDacStep,numAdcAverages,numAdcConversionSkips,adcConversionTime_us):
        """
        """
        dacN = len(dacPorts)
        adcN = len(adcPorts)

        dev = self.selectedDevice(c)
        command_parts = [
            "BOXCAR_BUFFER_RAMP",
            str(dacN),
            str(adcN),
            str(dacsteps),
            str(numAdcMeasuresPerDacStep),
            str(numAdcAverages),
            str(numAdcConversionSkips),
            str(adcConversionTime_us),
            *[str(ch) for ch in dacPorts],
            *[str(v) for v in ivoltages_1],
            *[str(v) for v in fvoltages_1],
            *[str(v) for v in ivoltages_2],
            *[str(v) for v in fvoltages_2],
            *[str(ch) for ch in adcPorts],
        ]
        yield dev.write(",".join(command_parts) + "\n")
        
        channels = []
        data = b''
        dev.setramping(True)
        try:
            nbytes = 0
            totalbytes = 2 * dacsteps * numAdcAverages * numAdcMeasuresPerDacStep * adcN * 4
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
                    while not data.endswith(b'\n'):
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
        rawData = yield self.boxcar_buffer_ramp_debug(c, dacPorts, adcPorts, ivoltages_1, fvoltages_1, ivoltages_2, fvoltages_2, dacsteps, numAdcMeasuresPerDacStep, numAdcAverages, numAdcConversionSkips, adcConversionTime_us)
        
        output = []
        period_length = numAdcMeasuresPerDacStep * 2
        
        for adcIndex in range(len(adcPorts)):
            data = rawData[adcIndex]
            adcOutput = []
            
            window_size = period_length * numAdcAverages
            for start in range(0, len(data), window_size):
                window = data[start:start + window_size]
                
                periods = [
                    window[i:i + period_length]
                    for i in range(0, len(window), period_length)
                ]
                
                if len(periods) < numAdcAverages:
                    print("INCOMPLETE WINDOW!")
                    continue # Skip incomplete windows
                
                periods_array = np.array(periods[:numAdcAverages])
                
                avg_period = np.mean(periods_array, axis=0)
                
                first_half = np.mean(avg_period[:numAdcMeasuresPerDacStep])
                second_half = np.mean(avg_period[numAdcMeasuresPerDacStep:])
                
                adcOutput.extend([first_half, second_half])
            
            output.append(adcOutput)
        
        returnValue(output)
    
    @setting(130, dacPorts='*i', adcPorts='*i', ivoltages_1='*v[]', fvoltages_1='*v[]', ivoltages_2='*v[]', fvoltages_2='*v[]', dacsteps='i',numAdcMeasuresPerDacStep='i',numAdcAverages='i', numAdcConversionSkips='i', adcConversionTime_us='i', returns='**v[]')#(*v[],*v[])')
    def boxcar_buffer_ramp_transient_delete(self,c,dacPorts,adcPorts,ivoltages_1,fvoltages_1,ivoltages_2,fvoltages_2,dacsteps,numAdcMeasuresPerDacStep,numAdcAverages,numAdcConversionSkips,adcConversionTime_us):
        """
        """
        rawData = yield self.boxcar_buffer_ramp_debug(c,dacPorts,adcPorts,ivoltages_1,fvoltages_1,ivoltages_2,fvoltages_2,dacsteps,numAdcMeasuresPerDacStep,numAdcAverages,numAdcConversionSkips,adcConversionTime_us)
        output = []
        for adcIndex in range(len(rawData)):
            data = rawData[adcIndex]
            group_size = numAdcAverages * 2 * numAdcMeasuresPerDacStep  # Total elements per group
    
            adcOutput = []
    
            total_length = len(data)
            num_full_groups = total_length // group_size
    
            for group_num in range(num_full_groups):
                start_idx = group_num * group_size
                end_idx = start_idx + group_size
                group = data[start_idx:end_idx]
    
                top_elements = []
                bottom_elements = []
    
                for cycle in range(numAdcAverages):
                    cycle_start = cycle * 2 * numAdcMeasuresPerDacStep
                    top_start = cycle_start
                    top_end = top_start + numAdcMeasuresPerDacStep
                    bottom_start = top_end
                    bottom_end = bottom_start + numAdcMeasuresPerDacStep
    
                    top = group[top_start:top_end]
                    bottom = group[bottom_start:bottom_end]
    
                    top_elements.extend(top)
                    bottom_elements.extend(bottom)
    
                average_top = sum(top_elements) / len(top_elements) if top_elements else 0
                average_bottom = sum(bottom_elements) / len(bottom_elements) if bottom_elements else 0
    
                difference = abs(average_top - average_bottom)
                adcOutput.append(difference)
    
            output.append(adcOutput)
            
        returnValue(output)
    '''
    @setting(133)
    def reset_adc(self,c):
        dev = self.selectedDevice(c)
        yield dev.write("RESET\n")
    
    @setting(220)
    def hard_reset_adc(self,c):
        dev = self.selectedDevice(c)
        yield dev.write("HARD_RESET\n")
        ans = yield dev.read()
        returnValue(ans)
        
    @setting(135, channel='i', returns='v[]')
    def get_conversion_time(self,c,channel):
        dev = self.selectedDevice(c)
        yield dev.write(f"GET_CONVERT_TIME,{channel}\n")
        ans = yield dev.read()
        returnValue(float(ans))
        
    @setting(201,adcPorts='*i', convtime='v[]', totalTime='v[]')
    def time_series_adc_read(self, c, adcPorts, convtime, totalTime):
        """
        TIME_SERIES_ADC_READ reads the specified ADC channels for a pre-determined length of time
        This function currently requires that all the ADCs being called have the same conversion time
        """
        adcN = len(adcPorts)
        
        dev = self.selectedDevice(c)
        command_parts = [
            "TIME_SERIES_ADC_READ",
            str(adcN),
            *[str(ch) for ch in adcPorts],
            str(convtime),
            str(totalTime),
        ]
        yield dev.write(",".join(command_parts) + "\n")
        self.sigSpectrumStarted([adcPorts, totalTime])
        
        channels = []
        data = b''
      
        dev.setramping(True)
        sampling_time_data = b''
        sampling_time_data += yield dev.readByte(4)
        sampling_time = np.frombuffer(sampling_time_data, dtype=np.float32)[0]
        
        try:
            nbytes = 0
            totalbytes = adcN * int(totalTime / sampling_time) * 4
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
                    while not data.endswith(b'\n'):
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

        try:
            yield dev.reset_input_buffer()
        except:
            print("Error clearing the serial buffer after buffer_ramp")
        returnValue(channels)
        
    
    @setting(108,dacPorts='*i', adcPorts='*i', ivoltages='*v[]', fvoltages='*v[]', steps='i',dacPeriod_us='v[]',adcPeriod_us='v[]',returns='**v[]')#(*v[],*v[])')
    def time_series_buffer_ramp(self,c,dacPorts,adcPorts,ivoltages,fvoltages,steps,dacPeriod_us,adcPeriod_us):
        """
        TIME_SERIES_BUFFER_RAMP ramps the specified output channels from the initial voltages to the final voltages and reads the specified input channels in a synchronized manner.
        It does it within an specified number steps, with DAC voltages being updated every dacPeriod_us and ADC voltages read every adcPeriod_us
        """

        dacN = len(dacPorts)
        adcN = len(adcPorts)

        dev = self.selectedDevice(c)
        command_parts = [
            "TIME_SERIES_BUFFER_RAMP",
            str(dacN),
            str(adcN),
            str(steps),
            str(dacPeriod_us),
            str(adcPeriod_us),
            *[str(ch) for ch in dacPorts],
            *[str(v) for v in ivoltages],
            *[str(v) for v in fvoltages],
            *[str(ch) for ch in adcPorts],
        ]
        yield dev.write(",".join(command_parts) + "\n")
        self.sigBufferRampStarted([dacPorts, adcPorts, ivoltages, fvoltages, str(steps), str(dacPeriod_us), str(adcPeriod_us)])

        channels = []
        data = b''
      
        
        dev.setramping(True)
        try:
            nbytes = 0
            totalbytes = int(steps * dacPeriod_us / adcPeriod_us) * adcN * 4
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
                    while not data.endswith(b'\n'):
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
        #if not (channel in self.channels):
        #    returnValue("Error: invalid channel. Must be in 0,1,2,3")
        if not (82 <= time <= 2686):
            returnValue("Error: invalid conversion time. Must adhere to (82 <= t <= 2686) (t is in microseconds)")
        dev=self.selectedDevice(c)
        yield dev.write("CONVERT_TIME,%i,%f\n"%(channel,time))
        ans = yield dev.read()
        self.sigConvTimeSet([str(channel),str(ans)])
        returnValue(float(ans))
    
    @setting(134,channel='i',fw='i',returns='v[]')
    def set_conversionTimeFW(self,c,channel,fw):
        """
        CONVERT_TIME sets the conversion time for the ADC. The conversion time is the time the ADC takes to convert the analog signal to a digital signal.
        Keep in mind that the smaller the conversion time, the more noise your measurements will have. Maximum conversion time: 2686 microseconds. Minimum conversion time: 82 microseconds.
        """
        #if not (channel in self.channels):
        #    returnValue("Error: invalid channel. Must be in 0,1,2,3")
        if not (3 <= fw <= 127):
            returnValue("Error: invalid conversion time. Must adhere to (3 <= fw <= 127)")
        dev=self.selectedDevice(c)
        yield dev.write("CONVERT_TIME_FW,%i,%f\n"%(channel,fw))
        ans = yield dev.read()
        # self.sigConvTimeSet([str(channel),str(ans)])
        returnValue(float(ans))


    @setting(110,returns='s')
    def id(self,c):
        """
        IDN? returns the string.
        """
        dev=self.selectedDevice(c)
        yield dev.write("*IDN?\n")
        time.sleep(1)
        ans = yield dev.read()
        returnValue(ans)

    @setting(111,returns='s')
    def ready(self,c):
        """
        RDY? returns the string "READY" when the DAC-ADC is ready for a new operation.
        """
        dev=self.selectedDevice(c)
        yield dev.write("*RDY?\n")
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
        yield dev.write("STOP\n")
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
        yield dev.write("DAC_CH_CAL\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(115,returns='s')
    def calibrate_all_adc_channels_zero_scale(self,c):
        """
        Calibrates ADC Zero scale for all channels.
        Connect a zero scale voltage to all channels.
        """
        dev=self.selectedDevice(c)
        yield dev.write("CALIBRATE_ALL_ADC_CHANNELS_ZERO_SCALE\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(116, channel='i', returns='s')
    def calibrate_adc_channel_zero_scale(self,c, channel):
        """
        Calibrates ADC Zero scale for specified channel.
        Connect a zero scale voltage to specified channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write(f"CALIBRATE_ADC_CHANNEL_ZERO_SCALE,{channel}\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(117, channel='i', returns='s')
    def calibrate_adc_channel_full_scale(self,c, channel):
        """
        Calibrates ADC Full scale for specified channel.
        Connect a full scale voltage to specified channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write(f"CALIBRATE_ADC_CHANNEL_FULL_SCALE,{channel}\n")
        ans = yield dev.read()
        returnValue(ans)
    
    @setting(140, returns='s')
    def calibrate_all_adc_channel_full_scale(self,c):
        """
        Calibrates ADC Full scale for specified channel.
        Connect a full scale voltage to specified channel.
        """
        dev=self.selectedDevice(c)
        yield dev.write(f"CALIBRATE_ALL_ADC_CHANNELS_FULL_SCALE\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(118,returns='s')
    def initialize(self,c):
        """
        Initializes DACs
        """
        dev=self.selectedDevice(c)
        yield dev.write("INITIALIZE\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(119,unit='i',returns='s')
    def delay_unit(self,c,unit):
        """
        Sets delay unit. 0 = microseconds(default) 1 = miliseconds
        """
        dev=self.selectedDevice(c)
        yield dev.write("SET_DUNIT,%i\n"%(unit))
        ans = yield dev.read()
        returnValue(ans)

    @setting(120,voltage='v',returns='s')
    def dac_full_scale(self,c,voltage):
        """
        Sets the dac full scale.
        """
        dev=self.selectedDevice(c)
        yield dev.write("FULL_SCALE,%f\n"%(voltage))
        ans = yield dev.read()
        returnValue(ans)

    @setting(136, channel='i', limit='v', returns='s')
    def setUpperLimit(self, c, channel, limit):
        """
        Sets the upper voltage limit for a specific DAC channel.
        """
        dev = self.selectedDevice(c)
        yield dev.write("SET_UPPER_LIMIT,%i,%f\n" % (int(channel), float(limit)))
        ans = yield dev.read()
        returnValue(ans)

    @setting(137, channel='i', limit='v', returns='s')
    def setLowerLimit(self, c, channel, limit):
        """
        Sets the lower voltage limit for a specific DAC channel.
        """
        dev = self.selectedDevice(c)
        yield dev.write("SET_LOWER_LIMIT,%i,%f\n" % (int(channel), float(limit)))
        ans = yield dev.read()
        returnValue(ans)
    
    @setting(138, channel='i', returns='v')
    def getLowerLimit(self, c, channel, limit):
        """
        Gets the lower voltage limit for a specific DAC channel.
        """
        dev = self.selectedDevice(c)
        yield dev.write("GET_LOWER_LIMIT,%i\n" % (int(channel)))
        ans = yield dev.read()
        returnValue(ans)
    
    @setting(139, channel='i', returns='v')
    def getUpperLimit(self, c, channel, limit):
        """
        Gets the upper voltage limit for a specific DAC channel.
        """
        dev = self.selectedDevice(c)
        yield dev.write("GET_UPPER_LIMIT,%i\n" % (int(channel)))
        ans = yield dev.read()
        returnValue(ans)

    @setting(121)
    def set_offset_and_gain(self,c,channel,offset,gain):
        """
        Set the offset and gain for all DAC channels.
        """
        dev=self.selectedDevice(c)
        message = f"SET_OSG,{channel},{offset},{gain}\n"
        yield dev.write(message)
        ans = yield dev.read()

        returnValue(ans)

    @setting(122)
    def inquiry_offset_and_gain(self,c):
        """
        Print the current offset and gain values for all DAC channels.
        """
        dev=self.selectedDevice(c)
        yield dev.write("INQUIRY_OSG\n")
        ans = [0]*32
        for i in range(32):
            ans[i] = yield dev.read()

        returnValue(ans)


    @setting(123)
    def sn(self,c):
        """
        Returns the serial number of the box.
        """
        dev = self.selectedDevice(c)
        yield dev.write("SERIAL_NUMBER\n")
        ans = yield dev.read()
        returnValue(ans)

    @setting(124,channel='i',code='i')
    def set_dac_code(self,c,channel,code):
        """
        SET_DAC_CODE writes a code between 0 and 1048576 to a channel and returns the channel and the code written to that DAC's register.
        """
        if not (channel in range(8)):
            returnValue("Error: invalid port number.")
            return
        if (code > 1048576) or (code < 0):
            returnValue("Error: invalid code. Must be between 0 and 1048576.")
            return
        dev=self.selectedDevice(c)
        yield dev.write("SET_DAC_CODE,%i,%i\n"%(channel,code))
        ans = yield dev.read()
        code = ans.lower().partition(' to ')[2][:-1]
        self.sigOutputSet([str(channel),code])
        returnValue(ans)

    @setting(125,channel='i')
    def read_dac_voltage(self,c,channel):
        """
        GET_DAC returns the most recent value to which the provided channel was set.
        """
        if not (channel in range(16)):
            returnValue("Error: invalid port number.")
        dev = self.selectedDevice(c)
        yield dev.write("GET_DAC,%i\n"%(channel))
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
        yield dev.write(f"{phrase}\n")
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
            yield dev.write("GET_ADC,%i\n"%port)
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


def parse_2d_ramp_line_payload(payload):
    """
    Decode a `sig2DRampLine` message into a plain dictionary.

    Returns a dict with fields such as `line_index`, `slow_param`,
    `fast_direction`, `slow_position`, `start_point`, `fast_axis_vector`,
    `slow_axis_vector`, `dac_ports`, `adc_ports`, and `channels`
    (ADC samples per channel).
    """
    if isinstance(payload, (list, tuple)):
        payload = payload[0]
    if isinstance(payload, bytes):
        payload = payload.decode('utf-8')
    data = json.loads(payload)

    data.setdefault("fast_direction", data.get("direction", "forward"))

    slow_position = data.get("slow_position")
    if slow_position is None:
        slow_position = data.get("slow_voltages", [])
    if slow_position is None:
        slow_position = []
    data["slow_position"] = [float(v) for v in slow_position]

    data["start_point"] = [float(v) for v in data.get("start_point", [])]
    data["fast_axis_vector"] = [float(v) for v in data.get("fast_axis_vector", [])]
    data["slow_axis_vector"] = [float(v) for v in data.get("slow_axis_vector", [])]
    data["adc_ports"] = list(data.get("adc_ports", []))
    data["dac_ports"] = list(data.get("dac_ports", []))

    channels = data.get("channels", [])
    data["channels"] = [[float(v) for v in channel] for channel in channels]

    return data


@inlineCallbacks
def _run_2d_ramp_with_callback(server, runner, runner_args, *,
                               line_callback=None, device_index=None):
    """
    Common helper that subscribes to `sig2DRampLine` while running a ramp.

    Each decoded line is passed to `line_callback`.  The underlying ramp
    (``runner``) is invoked with ``runner_args`` and its normal return value
    is propagated after the callback subscription is cleaned up.
    """
    if device_index is not None:
        try:
            yield server.select_device(device_index)
        except Exception as exc:
            print(f"Warning: failed to select device {device_index}: {exc}")

    if line_callback is None:
        def line_callback(_info):
            return None

    def handler(context, payload):
        try:
            info = parse_2d_ramp_line_payload(payload)
        except Exception as e:
            print("Error: failed to parse sig2DRampLine payload")
            print(e)
            return
        d = defer.maybeDeferred(line_callback, info)
        d.addErrback(lambda failure: print(f"Callback error: {failure}"))

    yield server.signal__2d_ramp_line.connect(handler)
    result = None
    try:
        result = yield runner(*runner_args)
    finally:
        try:
            yield server.signal__2d_ramp_line.disconnect(handler)
        except Exception as e:
            print(e)
            pass

    returnValue(result)


@inlineCallbacks
def time_series_buffer_ramp_2d_with_callback(server, dacPorts, adcPorts,
                                             startPoint, fastAxisVector,
                                             slowAxisVector, stepsFast,
                                             stepsSlow, retrace, snake,
                                             dacInterval_us, adcInterval_us,
                                             *, line_callback=None,
                                             device_index=None):
    """
    Run the time-series 2D ramp and stream each line into a Python callback.

    Args mirror the LabRAD setting.  When `line_callback` is supplied, it
    receives dictionaries produced by :func:`parse_2d_ramp_line_payload`
    (one per line).  If `device_index` is given, the helper selects that
    device before running.  Returns the ramp data exactly as the setting would.
    """
    result = yield _run_2d_ramp_with_callback(
        server,
        server.time_series_buffer_ramp_2d,
        (
            dacPorts,
            adcPorts,
            startPoint,
            fastAxisVector,
            slowAxisVector,
            stepsFast,
            stepsSlow,
            retrace,
            snake,
            dacInterval_us,
            adcInterval_us,
        ),
        line_callback=line_callback,
        device_index=device_index,
    )
    returnValue(result)


@inlineCallbacks
def dac_led_buffer_ramp_2d_with_callback(server, dacPorts, adcPorts,
                                         startPoint, fastAxisVector,
                                         slowAxisVector, stepsFast,
                                         stepsSlow, retrace, snake,
                                         numAdcAverages, dacInterval_us,
                                         dacSettlingTime_us, *,
                                         line_callback=None,
                                         device_index=None):
    """
    Run the LED 2D ramp while firing a Python callback for every line.

    Parameters match the LabRAD setting.  The optional `line_callback` is
    invoked with decoded dictionaries, allowing clients to save or process
    each line incrementally.  `device_index` selects a device before running.
    Returns the ramp data exactly as the setting would.
    """
    result = yield _run_2d_ramp_with_callback(
        server,
        server.dac_led_buffer_ramp_2d,
        (
            dacPorts,
            adcPorts,
            startPoint,
            fastAxisVector,
            slowAxisVector,
            stepsFast,
            stepsSlow,
            retrace,
            snake,
            numAdcAverages,
            dacInterval_us,
            dacSettlingTime_us,
        ),
        line_callback=line_callback,
        device_index=device_index,
    )
    returnValue(result)


def save_dac_led_buffer_ramp_2d(
    filename=None,
    *,
    dac_ports,
    adc_ports,
    start_point,
    fast_axis_vector,
    slow_axis_vector,
    steps_fast,
    steps_slow,
    retrace=False,
    snake=False,
    num_adc_averages=1,
    dac_period_us=1000.0,
    dac_settling_us=100.0,
    device_index=None,
):
    """
    Run a LED-style 2D sweep and dump every sample to an HDF5 file.

    Simple one-shot helper for “just give me a file.”  Under the hood it
    connects to LabRAD, runs :func:`dac_led_buffer_ramp_2d_with_callback`,
    and appends each line to ``filename`` (defaults to ./data/timestamp).  The
    dataset is named ``data`` and contains columns ``point_index``,
    ``line_index``, each DAC voltage, and each ADC voltage.  Basic sweep
    metadata (ports, vectors, step counts, etc.) are stored as attributes.

    Returns the :class:`pathlib.Path` of the created file.
    """
    if reactor.running:
        raise RuntimeError(
            "Twisted reactor already running; call save_dac_led_buffer_ramp_2d "
            "from a fresh process or manage the Deferred yourself."
        )

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = Path("data") / f"{timestamp}_2d_ramp.h5"
    else:
        filename = Path(filename)

    # lazy import to keep server lightweight if this helper is unused
    import h5py

    class _SimpleHDF5Saver(object):
        def __init__(self, filename, column_names, metadata):
            path = Path(filename).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.path = path
            self.file = h5py.File(self.path, "w")
            self.dataset = self.file.create_dataset(
                "data",
                shape=(0, len(column_names)),
                maxshape=(None, len(column_names)),
                dtype=np.float64,
                chunks=True,
            )
            self.dataset.attrs["column_names"] = column_names
            for key, value in metadata.items():
                self.dataset.attrs[key] = value
            self.rows_written = 0

        def append(self, rows):
            rows = np.asarray(rows, dtype=np.float64)
            if not rows.size:
                return
            start = self.rows_written
            stop = start + rows.shape[0]
            self.dataset.resize((stop, rows.shape[1]))
            self.dataset[start:stop, :] = rows
            self.rows_written = stop

        def close(self):
            if getattr(self, "file", None):
                self.file.flush()
                self.file.close()
                self.file = None

    column_names = (
        ["point_index", "line_index"]
        + [f"dac_{port}" for port in dac_ports]
        + [f"adc_{port}" for port in adc_ports]
    )

    metadata = {
        "dac_ports": list(dac_ports),
        "adc_ports": list(adc_ports),
        "start_point": list(start_point),
        "fast_axis_vector": list(fast_axis_vector),
        "slow_axis_vector": list(slow_axis_vector),
        "steps_fast": int(steps_fast),
        "steps_slow": int(steps_slow),
        "retrace": bool(retrace),
        "snake": bool(snake),
        "num_adc_averages": int(num_adc_averages),
        "dac_period_us": float(dac_period_us),
        "dac_settling_us": float(dac_settling_us),
    }
    saver = _SimpleHDF5Saver(filename, column_names, metadata)
    start = np.asarray(start_point, dtype=float)
    fast = np.asarray(fast_axis_vector, dtype=float)
    slow = np.asarray(slow_axis_vector, dtype=float)
    dac_ports = list(dac_ports)
    adc_ports = list(adc_ports)

    total_lines = steps_slow * (2 if retrace and not snake else 1)
    slow_denominator = steps_slow - 1 if steps_slow > 1 else 1

    def handle_line(info):
        line_idx = int(info.get("line_index", 0))
        if line_idx < 0 or line_idx >= total_lines:
            return
        channels = info.get("channels", [])
        length_candidates = [len(values) for values in channels if values]
        if not length_candidates:
            return
        length = max(length_candidates)
        if length <= 0:
            return

        if retrace and not snake:
            slow_step = line_idx // 2
            is_forward = (line_idx % 2) == 0
        else:
            slow_step = line_idx
            is_forward = (not snake) or (slow_step % 2 == 0)

        slow_param = float(slow_step) / slow_denominator if slow_denominator else 0.0
        slow_position = start + slow_param * slow

        fast_fraction = np.linspace(0.0, 1.0, length, dtype=float)
        if not is_forward:
            fast_fraction = fast_fraction[::-1]

        dac_rows = slow_position[None, :] + fast_fraction[:, None] * fast

        adc_matrix = np.full((length, len(adc_ports)), np.nan, dtype=float)
        for idx, values in enumerate(channels[: len(adc_ports)]):
            arr = np.asarray(values, dtype=float)
            count = min(len(arr), length)
            adc_matrix[:count, idx] = arr[:count]

        point_idx = np.arange(length, dtype=float)
        line_idx_column = np.full(length, float(line_idx), dtype=float)

        rows = np.column_stack([point_idx, line_idx_column, dac_rows, adc_matrix])
        saver.append(rows)

    @inlineCallbacks
    def _main():
        cxn = None
        failed = False
        error = None
        try:
            cxn = yield connectAsync()
            server = cxn.dac_adc_giga
            if device_index is not None:
                yield server.select_device(device_index)
            yield dac_led_buffer_ramp_2d_with_callback(
                server,
                dac_ports,
                adc_ports,
                start.tolist(),
                fast.tolist(),
                slow.tolist(),
                steps_fast,
                steps_slow,
                retrace,
                snake,
                num_adc_averages,
                dac_period_us,
                dac_settling_us,
                line_callback=handle_line,
            )
        except Exception as exc:
            failed = True
            error = exc
        finally:
            saver.close()
            if cxn is not None:
                yield cxn.disconnect()
            if failed:
                print(f"Ramp failed: {error}")
            else:
                print(f"Saved {saver.rows_written} rows to {saver.path}")
            reactor.stop()

    reactor.callWhenRunning(lambda: defer.ensureDeferred(_main()))
    reactor.run()
    return saver.path


def parse_awg_data_payload(payload):
    """
    Decode a `sigAWGData` message into a plain dictionary.

    Returns a dict with fields `reading_index`, `adc_ports`, and `values`.
    """
    if isinstance(payload, (list, tuple)):
        payload = payload[0]
    if isinstance(payload, bytes):
        payload = payload.decode('utf-8')
    data = json.loads(payload)
    data["reading_index"] = int(data.get("reading_index", 0))
    data["adc_ports"] = list(data.get("adc_ports", []))
    data["values"] = [float(v) for v in data.get("values", [])]
    return data


@inlineCallbacks
def awg_with_adc_with_callback(server, dacPorts, adcPorts, voltageLists,
                                dacInterval_us, numCycles=1, *,
                                reading_callback=None, device_index=None):
    """
    Run AWG_WITH_ADC and stream each ADC reading into a Python callback.

    Args:
        server: The LabRAD DAC-ADC server connection
        dacPorts: Sequence of DAC channel IDs
        adcPorts: Sequence of ADC channel IDs
        voltageLists: Voltage arrays for each DAC channel
        dacInterval_us: Time between DAC updates in microseconds
        numCycles: Number of times to repeat the waveform
        reading_callback: Called for each ADC reading with decoded dict
        device_index: Optional device index to select before running

    Returns:
        The ramp data as returned by the setting
    """
    if device_index is not None:
        try:
            yield server.select_device(device_index)
        except Exception as exc:
            print(f"Warning: failed to select device {device_index}: {exc}")

    if reading_callback is None:
        def reading_callback(_info):
            return None

    def handler(context, payload):
        try:
            info = parse_awg_data_payload(payload)
        except Exception as e:
            print("Error: failed to parse sigAWGData payload")
            print(e)
            return
        d = defer.maybeDeferred(reading_callback, info)
        d.addErrback(lambda failure: print(f"Callback error: {failure}"))

    yield server.signal__awg_data.connect(handler)
    result = None
    try:
        result = yield server.awg_with_adc(dacPorts, adcPorts, voltageLists,
                                            dacInterval_us, numCycles)
    finally:
        try:
            yield server.signal__awg_data.disconnect(handler)
        except Exception as e:
            print(e)
            pass

    returnValue(result)


def save_awg_with_adc(
    filename=None,
    *,
    dac_ports,
    adc_ports,
    voltage_lists,
    dac_interval_us,
    num_cycles=1,
    device_index=None,
):
    """
    Run AWG_WITH_ADC and save all ADC readings to an HDF5 file.

    Args:
        filename: Path to HDF5 file (default: ./data/timestamp_awg.h5)
        dac_ports: Sequence of DAC channel IDs
        adc_ports: Sequence of ADC channel IDs
        voltage_lists: Voltage arrays for each DAC channel
        dac_interval_us: Time between DAC updates in microseconds
        num_cycles: Number of times to repeat the waveform
        device_index: Optional device index to select

    Returns:
        Path to the created HDF5 file
    """
    if reactor.running:
        raise RuntimeError(
            "Twisted reactor already running; call save_awg_with_adc "
            "from a fresh process or manage the Deferred yourself."
        )

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = Path("data") / f"{timestamp}_awg.h5"
    else:
        filename = Path(filename)

    import h5py

    class _AWGDataSaver(object):
        def __init__(self, filename, column_names, metadata):
            path = Path(filename).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.path = path
            self.file = h5py.File(self.path, "w")
            self.dataset = self.file.create_dataset(
                "data",
                shape=(0, len(column_names)),
                maxshape=(None, len(column_names)),
                dtype=np.float64,
                chunks=True,
            )
            self.dataset.attrs["column_names"] = column_names
            for key, value in metadata.items():
                self.dataset.attrs[key] = value
            self.rows_written = 0

        def append(self, rows):
            rows = np.asarray(rows, dtype=np.float64)
            if not rows.size:
                return
            start = self.rows_written
            stop = start + rows.shape[0]
            self.dataset.resize((stop, rows.shape[1]))
            self.dataset[start:stop, :] = rows
            self.rows_written = stop

        def close(self):
            if getattr(self, "file", None):
                self.file.flush()
                self.file.close()
                self.file = None

    dac_ports = list(dac_ports)
    adc_ports = list(adc_ports)
    num_steps = len(voltage_lists[0]) if voltage_lists else 0

    column_names = (
        ["reading_index", "time_us"]
        + [f"adc_{port}" for port in adc_ports]
    )

    metadata = {
        "dac_ports": dac_ports,
        "adc_ports": adc_ports,
        "num_steps": num_steps,
        "num_cycles": int(num_cycles),
        "dac_interval_us": float(dac_interval_us),
        "voltage_lists": [list(v) for v in voltage_lists],
    }

    saver = _AWGDataSaver(filename, column_names, metadata)

    # Get conversion time later to compute time axis
    conv_time_us = [500.0]  # will be updated

    def handle_reading(info):
        reading_idx = info.get("reading_index", 0)
        values = info.get("values", [])

        # Approximate time based on conversion time
        time_us = (reading_idx + 1) * conv_time_us[0]

        row = [float(reading_idx), time_us] + [float(v) for v in values]
        saver.append([row])

    @inlineCallbacks
    def _main():
        cxn = None
        failed = False
        error = None
        try:
            cxn = yield connectAsync()
            server = cxn.dac_adc_giga
            if device_index is not None:
                yield server.select_device(device_index)

            # Get actual conversion time
            if adc_ports:
                conv_time_us[0] = yield server.get_conversion_time(adc_ports[0])

            yield awg_with_adc_with_callback(
                server,
                dac_ports,
                adc_ports,
                voltage_lists,
                dac_interval_us,
                num_cycles,
                reading_callback=handle_reading,
            )
        except Exception as exc:
            failed = True
            error = exc
        finally:
            saver.close()
            if cxn is not None:
                yield cxn.disconnect()
            if failed:
                print(f"AWG failed: {error}")
            else:
                print(f"Saved {saver.rows_written} rows to {saver.path}")
            reactor.stop()

    reactor.callWhenRunning(lambda: defer.ensureDeferred(_main()))
    reactor.run()
    return saver.path


__server__ = DAC_ADCServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
