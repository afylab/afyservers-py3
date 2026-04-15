from itertools import chain
import labrad
import numpy as np
import matplotlib.pyplot as plt
from time import sleep

"""
1) set dac code to 0
2) read ag value
3) see direction of change
4) if positive, increment dac code
5) if negative, decrement dac code
6) repeat until voltage is within 1 LSB of 0
7) increment/decrement by 1 more code and see if that code is better
8) print dac code and ag value
9) set offset to the voltage corresponding to the dac code
10) set gain to 1
11) set voltage to 10 V
12) read ag value
13) calculate gain = ag value / 10
14) set gain
"""

channel = 0

lsb_size = 20/(2**20 - 1) # V


def dac_code_to_voltage(dac_code):
    if dac_code <= 524287:
        return dac_code * 10 / 524287
    else:
        return (dac_code - 1048576) * 10 / 524288


def voltage_to_dac_code(voltage):
    if voltage >= 0:
        return int(voltage * 524287 / 10)
    else:
        return int(voltage * 524288 / 10) + 1048576


cxn = labrad.connect()

da = cxn.dac_adc_giga()
da.select_device()
da.initialize()

ag = cxn.agilent_34401a_dmm()
ag.select_device()

### calibrate offset

# quickly find heuristic
ag.configure_voltage(10, 0.00001)

dac_code = 0
da.set_dac_code(channel,dac_code)
sleep(0.1)
old_ag_value = ag.read_voltage()

heuristic_dac_code = voltage_to_dac_code(-1.0 * old_ag_value)

ag.configure_voltage(0.01, 0.0000001)
da.set_dac_code(channel,heuristic_dac_code)
sleep(0.1)
ag_value = ag.read_voltage()
print(f"HEURISTIC DAC CODE: {heuristic_dac_code}, AG VALUE: {ag_value}")

# sweep until +/- 1 LSB measured.
# ag.configure_voltage(0.01, 0.0000001)

dac_code = heuristic_dac_code
da.set_dac_code(channel,dac_code)
sleep(0.1)
ag_value = ag.read_voltage()

MAX_CODE = 2**20 - 1

if ag_value > 0:
    direction = -1
else:
    direction = 1


while abs(ag_value) > lsb_size:
    dac_code = (dac_code + direction) % (MAX_CODE + 1)
    da.set_dac_code(channel, dac_code)
    sleep(0.1)
    ag_value = ag.read_voltage()

dac_code = (dac_code + direction) % (MAX_CODE + 1)

da.set_dac_code(channel,dac_code)
sleep(0.1)
ag_value_2 = ag.read_voltage()


if abs(ag_value_2) < abs(ag_value):
    ag_value = ag_value_2
else:
    dac_code = (dac_code - direction) % (MAX_CODE + 1)

da.set_dac_code(channel,dac_code)

print(f"DAC code: {dac_code}, AG value: {ag_value}")

offset = -dac_code_to_voltage(dac_code)

da.set_offset_and_gain(channel, offset, 1)

da.set_voltage(channel, 0)

print(f"OFFSET CALIBRATED. OLD 0 V = {old_ag_value} V; NEW 0 V = {ag.read_voltage()} V")

### calibrate gain

ag.configure_voltage(10, 0.00001)

da.set_voltage(channel, 10)
sleep(0.1)
ag_value = ag.read_voltage()
old_10v = ag_value

gain = ag_value/10

da.set_offset_and_gain(channel, offset, gain)

da.set_voltage(channel, 10)

print(f"GAIN CALIBRATED. OLD 10 V = {old_10v} V; NEW 10 V = {ag.read_voltage()} V")