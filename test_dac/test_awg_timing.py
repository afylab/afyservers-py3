#!/usr/bin/env python3
"""Test AWG_WITH_ADC timing - verify actual interval matches specified interval."""

import serial
import time
import struct
import glob

def find_serial_port():
    ports = glob.glob("/dev/cu.usbmodem*")
    return ports[0] if ports else "/dev/cu.usbmodem21201"

PORT = find_serial_port()
BAUD = 115200

def send_command(ser, cmd, timeout=0.3):
    ser.reset_input_buffer()
    ser.write(f"{cmd}\r\n".encode())
    ser.flush()
    time.sleep(timeout)
    return ser.read(1000).decode('utf-8', errors='ignore').strip()

def test_timing(interval_us, duration_s=0.5):
    """Test AWG timing at specified interval."""
    print(f"\n--- Testing {interval_us}us interval ---")

    ser = serial.Serial(PORT, BAUD, timeout=0.5)
    time.sleep(0.3)
    ser.reset_input_buffer()

    # Initialize
    response = send_command(ser, "INITIALIZE", 0.5)
    if "COMPLETE" not in response:
        print(f"Init failed: {response}")
        ser.close()
        return None

    # Simple 2-step square wave: 0V and 1V
    cmd = f"AWG_WITH_ADC,1,1,2,{interval_us},0,0,0.0,1.0"
    print(f"Command: {cmd}")

    ser.reset_input_buffer()
    start_time = time.time()
    ser.write(f"{cmd}\r\n".encode())
    ser.flush()

    # Collect data
    adc_data = b''
    while (time.time() - start_time) < duration_s:
        chunk = ser.read(256)
        if chunk:
            adc_data += chunk

    # Stop
    ser.write(b"STOP\r\n")
    ser.flush()
    time.sleep(0.1)
    ser.read(1000)

    # Cleanup
    send_command(ser, "SET,0,0.0", 0.1)
    ser.close()

    # Parse readings
    num_floats = len(adc_data) // 4
    readings = []
    for i in range(num_floats):
        value = struct.unpack('<f', adc_data[i*4:(i+1)*4])[0]
        readings.append(value)

    if num_floats < 10:
        print(f"Not enough data: {num_floats} readings")
        return None

    # Calculate actual timing
    # Each reading is one step, steps alternate 0V and 1V
    # So if we get N readings in T seconds, actual interval = T/N
    actual_interval_us = (duration_s * 1_000_000) / num_floats

    print(f"Collected {num_floats} readings in {duration_s}s")
    print(f"Expected interval: {interval_us}us")
    print(f"Actual interval:   {actual_interval_us:.1f}us")
    print(f"Ratio (actual/expected): {actual_interval_us/interval_us:.2f}x")

    # Show first few readings to verify alternating pattern
    print(f"First 10 readings: {[f'{r:.3f}' for r in readings[:10]]}")

    return actual_interval_us

def main():
    print(f"Using port: {PORT}")
    print("Testing AWG_WITH_ADC timing at different intervals")
    print("=" * 60)

    # Test various intervals
    for interval in [100, 200, 300, 400, 500, 600, 800, 1000]:
        test_timing(interval)

    print("\n" + "=" * 60)
    print("Done")

if __name__ == "__main__":
    main()
