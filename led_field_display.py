import labrad
import serial
import time
import sys, signal

cxn = labrad.connect()
mag = cxn.ami_430
mag.select_device()

signal.signal(signal.SIGINT, signal.default_int_handler)
led = serial.Serial('COM46',9600,timeout=0.2)
led.flush()
time.sleep(2)

isramping = mag.state()
if isramping == 1:
    led.write(b"m1")
else:
    led.write(b"m0")

led.write(b'c0,2,1')

while True:
    try:
        try:
            led.write(("f" + mag.get_field_mag()[0:5]).encode())
            if isramping != mag.state():
                isramping = mag.state()
                if isramping == 1:
                    led.write(b"m1")
                else:
                    led.write(b"m0")
        except ValueError as e:
            print(e)
        time.sleep(2)
    except KeyboardInterrupt:
        led.write("f(-_-)")
        led.close()
        sys.exit()
