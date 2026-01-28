#!/usr/bin/env python3
"""Test AWG_WITH_ADC: Set DAC values and read ADC immediately after each."""

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

def test_awg_with_adc():
    """Test AWG_WITH_ADC with a simple 5-step ramp, comparing DAC0 to ADC0."""
    print("=" * 60)
    print("Test: AWG_WITH_ADC - DAC/ADC Synchronization")
    print("DAC0 outputs voltages, ADC0 reads them back immediately")
    print("=" * 60)

    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.5)
        time.sleep(0.3)
        ser.reset_input_buffer()

        # Initialize
        response = send_command(ser, "INITIALIZE", 0.5)
        if "COMPLETE" not in response:
            print(f"Init failed: {response}")
            ser.close()
            return False
        print("Initialized")

        # Test parameters
        dac_n = 1
        adc_n = 1
        num_steps = 5
        interval_us = 1000  # 1ms per step
        dac_ch = 0
        adc_ch = 0
        expected_voltages = [-5.0, -2.5, 0.0, 2.5, 5.0]
        tolerance = 0.1  # 100mV tolerance for synchronization test

        # Build command
        cmd_parts = [
            "AWG_WITH_ADC",
            str(dac_n),
            str(adc_n),
            str(num_steps),
            str(interval_us),
            str(dac_ch),
            str(adc_ch),
        ]
        cmd_parts.extend([str(v) for v in expected_voltages])
        cmd = ",".join(cmd_parts)

        print(f"Command: {cmd}")
        print(f"Running AWG with {num_steps} steps at {interval_us}us intervals...")

        # Send command
        ser.reset_input_buffer()
        ser.write(f"{cmd}\r\n".encode())
        ser.flush()

        # Read binary ADC data while AWG runs
        adc_data = b''
        start_time = time.time()
        read_duration = 0.3  # Read for 300ms

        while (time.time() - start_time) < read_duration:
            chunk = ser.read(256)
            if chunk:
                adc_data += chunk

        # Stop AWG
        ser.write(b"STOP\r\n")
        ser.flush()
        time.sleep(0.2)
        ser.read(1000)  # Clear stop response

        print(f"\nCollected {len(adc_data)} bytes ({len(adc_data)//4} readings)")

        # Parse the collected ADC data (4-byte floats)
        if len(adc_data) < 4 * num_steps:
            print(f"ERROR: Not enough data collected (need at least {4*num_steps} bytes)")
            ser.close()
            return False

        num_floats = len(adc_data) // 4
        readings = []
        for i in range(num_floats):
            value = struct.unpack('<f', adc_data[i*4:(i+1)*4])[0]
            readings.append(value)

        # Validate readings - check that each expected voltage appears in order
        print(f"\nValidating synchronization (tolerance: ±{tolerance}V):")
        print(f"{'Step':>6} {'Expected':>10} {'ADC Mean':>10} {'Error':>10} {'Status':>8}")
        print("-" * 50)

        all_passed = True
        cycles_found = 0

        # Check first cycle only (for simplicity)
        for step, expected in enumerate(expected_voltages):
            actual = readings[step]
            error = abs(actual - expected)
            passed = error < tolerance
            status = "PASS" if passed else "FAIL"
            if not passed:
                all_passed = False
            print(f"{step:>6} {expected:>10.4f} {actual:>10.4f} {error:>10.4f} {status:>8}")
        cycles_found = 1

        print("-" * 50)

        # Additional statistics
        print(f"\nStatistics:")
        print(f"  Total readings: {num_floats}")
        print(f"  Full cycles validated: {cycles_found}")
        print(f"  Voltage range: [{min(readings):.4f}, {max(readings):.4f}]")

        # Check unique values (should have variation)
        unique_count = len(set(struct.pack('<f', v).hex() for v in readings))
        print(f"  Unique values: {unique_count}")

        # Cleanup
        send_command(ser, "SET,0,0.0", 0.2)
        ser.close()

        print("\n" + "=" * 60)
        result = "ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"
        print(f"Result: {result}")
        print("=" * 60)
        return all_passed

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print(f"Using port: {PORT}\n")
    return test_awg_with_adc()

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
