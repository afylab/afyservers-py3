from itertools import chain
import labrad
import numpy as np
import matplotlib.pyplot as plt

channel = 0

lsb_size = 20/(2**20 - 1) # V

cxn = labrad.connect()

da = cxn.dac_adc_giga()
da.select_device()

ag = cxn.agilent_34401a_dmm()
ag.select_device()

ag.configure_voltage(0.1, 0.000001)

da.initialize()

da.set_dac_code(channel,0)

ag_value = ag.read_voltage()


if ag_value > 0:
    direction = -1
else:
    direction = 1

while abs(ag_value) > lsb_size:
    da.set_dac_code(channel,dac_code)
    ag_value = ag.read_voltage()
    dac_code += direction

da.set_dac_code(channel,dac_code)
ag_value_2 = ag.read_voltage()


if abs(ag_value_2) < abs(ag_value):
    ag_value = ag_value_2
else:
    dac_code -= direction

print(f"DAC code: {dac_code}, AG value: {ag_value}")


"""
1) set dac code to 0
2) read ag value
3) see direction of change
4) if positive, increment dac code
5) if negative, decrement dac code
6) repeat until voltage is within 1 LSB of 0
7) increment/decrement by 1 more code and see if that code is better
8) return dac code and ag value
"""