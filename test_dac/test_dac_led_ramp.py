#!/usr/bin/env python3
"""Test script for DAC_LED_BUFFER_RAMP - ramps DAC while reading ADC."""

import serial
import time
import sys
import struct
import glob

def find_serial_port():
    """Find the Arduino serial port."""
    ports = glob.glob("/dev/cu.usbmodem*")
    if ports:
        return ports[0]
    return "/dev/cu.usbmodem21201"

PORT = find_serial_port()
BAUD = 115200

def send_command(ser, cmd, timeout=0.3):
    """Send command and get response."""
    ser.reset_input_buffer()
    ser.write(f"{cmd}\r\n".encode())
    ser.flush()
    time.sleep(timeout)
    return ser.read(500).decode('utf-8', errors='ignore').strip()

def read_floats(ser, count, timeout=5.0):
    """Read binary float data from serial."""
    floats = []
    start_time = time.time()
    bytes_needed = count * 4  # 4 bytes per float
    data = b''

    while len(data) < bytes_needed and (time.time() - start_time) < timeout:
        chunk = ser.read(bytes_needed - len(data))
        if chunk:
            data += chunk
        else:
            time.sleep(0.01)

    if len(data) >= bytes_needed:
        for i in range(count):
            value = struct.unpack('<f', data[i*4:(i+1)*4])[0]
            floats.append(value)

    return floats

def test_dac_led_ramp():
    """
    Test DAC_LED_BUFFER_RAMP: Ramp DAC 0 from -10V to 10V in 10 steps,
    reading ADC 0 at each step. Verify ADC readings match expected DAC voltages.
    """
    print(f"Using port: {PORT}")
    print("=" * 60)
    print("DAC_LED_BUFFER_RAMP Test")
    print("Ramp DAC 0 from -5V to 5V in 10 steps at 1kHz, reading ADC 0")
    print("=" * 60)

    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.5)
        time.sleep(0.3)
        ser.reset_input_buffer()

        # Initialize
        print("\n1. Initializing...")
        response = send_command(ser, "INITIALIZE", 0.5)
        if "COMPLETE" not in response and "INITIALIZATION" not in response:
            print(f"   FAIL: {response}")
            ser.close()
            return False
        print("   PASS: Initialized")

        # Parameters for the ramp
        num_dac_channels = 1
        num_adc_channels = 1
        num_steps = 10
        num_adc_averages = 1
        dac_interval_us = 1000  # 1ms per step (1kHz) - fast but within ADC limits
        dac_settling_time_us = 200  # 200us settling time

        dac_channel = 0
        dac_v0 = -5.0
        dac_vf = 5.0
        adc_channel = 0

        # Expected voltages at each step
        step_size = (dac_vf - dac_v0) / (num_steps - 1)
        expected_voltages = [dac_v0 + i * step_size for i in range(num_steps)]

        # Pre-set DAC to starting voltage to ensure clean start
        print(f"\n2. Pre-setting DAC to starting voltage ({dac_v0}V)...")
        response = send_command(ser, f"SET,{dac_channel},{dac_v0}", 0.3)
        print(f"   SET Response: {response}")
        time.sleep(0.1)

        # Verify DAC is at the right voltage
        response = send_command(ser, f"GET_DAC,{dac_channel}", 0.2)
        print(f"   GET_DAC Response: {response}")
        response = send_command(ser, f"GET_ADC,{adc_channel}", 0.2)
        print(f"   GET_ADC Response: {response} (should be ~{dac_v0}V)")
        time.sleep(0.1)

        print(f"\n3. Running DAC_LED_BUFFER_RAMP...")
        print(f"   DAC channel: {dac_channel}")
        print(f"   ADC channel: {adc_channel}")
        print(f"   Steps: {num_steps}")
        print(f"   Voltage range: {dac_v0}V to {dac_vf}V")
        print(f"   Interval: {dac_interval_us}us, Settling: {dac_settling_time_us}us")

        # Build command
        cmd = f"DAC_LED_BUFFER_RAMP,{num_dac_channels},{num_adc_channels},{num_steps},{num_adc_averages},{dac_interval_us},{dac_settling_time_us},{dac_channel},{dac_v0},{dac_vf},{adc_channel}"
        print(f"   Command: {cmd}")

        # Send command and wait for it to start
        ser.reset_input_buffer()
        ser.write(f"{cmd}\r\n".encode())
        ser.flush()

        # Read the ADC values (binary floats)
        # The ramp sends num_steps * num_adc_channels floats
        total_floats = num_steps * num_adc_channels
        print(f"\n4. Reading {total_floats} ADC values...")

        adc_values = read_floats(ser, total_floats, timeout=10.0)

        if len(adc_values) != total_floats:
            print(f"   FAIL: Expected {total_floats} values, got {len(adc_values)}")
            ser.close()
            return False

        print(f"   Received {len(adc_values)} values")

        # Read the completion message
        time.sleep(0.2)
        completion = ser.read(500).decode('utf-8', errors='ignore').strip()
        print(f"   Completion: {completion}")

        # Verify ADC readings match expected DAC voltages
        print(f"\n5. Verifying ADC readings match DAC voltages...")
        print(f"   {'Step':<6} {'Expected V':<12} {'ADC V':<12} {'Error V':<12} {'Status'}")
        print("   " + "-" * 54)

        tolerance = 0.1  # 100mV tolerance
        all_pass = True

        for i, (expected, actual) in enumerate(zip(expected_voltages, adc_values)):
            error = actual - expected
            status = "PASS" if abs(error) <= tolerance else "FAIL"
            if status == "FAIL":
                all_pass = False
            print(f"   {i:<6} {expected:<12.4f} {actual:<12.4f} {error:<12.4f} {status}")

        # Reset DAC to 0V
        print("\n6. Cleanup: Setting DAC 0 to 0V...")
        send_command(ser, "SET,0,0.0", 0.2)

        ser.close()

        print("\n" + "=" * 60)
        if all_pass:
            print("RESULT: ALL STEPS PASSED")
        else:
            print("RESULT: SOME STEPS FAILED")
        print("=" * 60)

        return all_pass

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_dac_led_ramp()
    sys.exit(0 if success else 1)
