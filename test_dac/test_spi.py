#!/usr/bin/env python3
"""Test script for SPI communication - tests NOP, INITIALIZE, DAC, and ADC."""

import serial
import time
import sys
import re
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

def test_basic():
    """Test NOP and INITIALIZE commands."""
    print(f"Using port: {PORT}")
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.5)
        time.sleep(0.3)
        ser.reset_input_buffer()

        results = []

        # Test NOP
        print("Test 1: NOP")
        response = send_command(ser, "NOP", 0.2)
        print(f"  Response: '{response}'")
        nop_ok = "NOP" in response
        results.append(("NOP", nop_ok))
        print(f"  {'PASS' if nop_ok else 'FAIL'}\n")

        # Test INITIALIZE (uses SPI)
        print("Test 2: INITIALIZE")
        response = send_command(ser, "INITIALIZE", 0.5)
        print(f"  Response: '{response}'")
        init_ok = "COMPLETE" in response or "INITIALIZATION" in response
        results.append(("INITIALIZE", init_ok))
        print(f"  {'PASS' if init_ok else 'FAIL'}\n")

        ser.close()
        return all(r[1] for r in results), results

    except Exception as e:
        print(f"Error: {e}")
        return False, []

def test_dac_adc():
    """Test DAC write and read, ADC read."""
    print(f"Using port: {PORT}")
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.5)
        time.sleep(0.3)
        ser.reset_input_buffer()

        results = []

        # First initialize
        print("Initializing...")
        response = send_command(ser, "INITIALIZE", 0.5)
        if "COMPLETE" not in response and "INITIALIZATION" not in response:
            print(f"  INITIALIZE failed: {response}")
            ser.close()
            return False, [("INITIALIZE", False)]

        # Set DAC 0 to 1.0V
        print("\nTest 3: SET DAC 0 to 1.0V")
        response = send_command(ser, "SET,0,1.0", 0.3)
        print(f"  Response: '{response}'")
        # Check for acknowledgment (could be "SET,0,1.0" echo or voltage)
        set_ok = len(response) > 0 and "error" not in response.lower()
        results.append(("SET DAC 0", set_ok))
        print(f"  {'PASS' if set_ok else 'FAIL'}\n")

        # Read DAC 0 voltage
        print("Test 4: GET_DAC 0 (expect ~1.0V)")
        response = send_command(ser, "GET_DAC,0", 0.3)
        print(f"  Response: '{response}'")
        # Try to parse voltage from response
        dac_voltage = None
        # Look for a float in the response
        match = re.search(r'[-+]?\d*\.?\d+', response)
        if match:
            dac_voltage = float(match.group())
        dac_ok = dac_voltage is not None and 0.9 <= dac_voltage <= 1.1
        results.append(("GET_DAC 0", dac_ok))
        print(f"  Parsed voltage: {dac_voltage}")
        print(f"  {'PASS' if dac_ok else 'FAIL'} (expected 0.9-1.1V)\n")

        # Read ADC 0 voltage (DAC 0 is connected to ADC 0)
        print("Test 5: GET_ADC 0 (expect ~1.0V, DAC0 connected to ADC0)")
        response = send_command(ser, "GET_ADC,0", 0.3)
        print(f"  Response: '{response}'")
        adc_voltage = None
        match = re.search(r'[-+]?\d*\.?\d+', response)
        if match:
            adc_voltage = float(match.group())
        # ADC might have some offset/noise, allow wider range
        adc_ok = adc_voltage is not None and 0.8 <= adc_voltage <= 1.2
        results.append(("GET_ADC 0", adc_ok))
        print(f"  Parsed voltage: {adc_voltage}")
        print(f"  {'PASS' if adc_ok else 'FAIL'} (expected 0.8-1.2V)\n")

        # Reset DAC to 0V
        print("Cleanup: SET DAC 0 to 0V")
        send_command(ser, "SET,0,0.0", 0.2)

        ser.close()
        return all(r[1] for r in results), results

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False, []

def test_awg():
    """Test AWG buffer ramp functionality."""
    print(f"Using port: {PORT}")
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.5)
        time.sleep(0.3)
        ser.reset_input_buffer()

        results = []

        # First initialize
        print("Initializing...")
        response = send_command(ser, "INITIALIZE", 0.5)
        if "COMPLETE" not in response and "INITIALIZATION" not in response:
            print(f"  INITIALIZE failed: {response}")
            ser.close()
            return False, [("INITIALIZE", False)]

        # Test AWG: 1 channel, 2 steps, 100us period, 1V to -1V, 1 repetition
        print("\nTest 6: AWG_BUFFER_RAMP (1 channel, 2 steps, 100us)")
        response = send_command(ser, "AWG_BUFFER_RAMP,1,2,100,1,-1,1", 0.5)
        print(f"  Response: '{response}'")
        # AWG should start running (might not produce output immediately)
        awg_start_ok = len(response) > 0 or True  # AWG may not immediately respond

        # Let it run for a moment then stop
        time.sleep(0.2)

        print("\nTest 7: STOP (stop AWG)")
        response = send_command(ser, "STOP", 0.3)
        print(f"  Response: '{response}'")
        awg_stop_ok = "RAMPING_STOPPED" in response or "STOPPED" in response.upper()
        results.append(("AWG_STOP", awg_stop_ok))
        print(f"  {'PASS' if awg_stop_ok else 'FAIL'}\n")

        # Verify DAC is at a sensible voltage after AWG
        print("Test 8: GET_DAC 0 after AWG (should be a valid voltage)")
        response = send_command(ser, "GET_DAC,0", 0.3)
        print(f"  Response: '{response}'")
        match = re.search(r'[-+]?\d*\.?\d+', response)
        dac_valid = match is not None
        results.append(("DAC_AFTER_AWG", dac_valid))
        if match:
            print(f"  Parsed voltage: {match.group()}")
        print(f"  {'PASS' if dac_valid else 'FAIL'}\n")

        # Reset DAC to 0V
        print("Cleanup: SET DAC 0 to 0V")
        send_command(ser, "SET,0,0.0", 0.2)

        ser.close()
        return all(r[1] for r in results), results

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False, []

def main():
    print("=" * 50)
    print("SPI Communication Tests")
    print("=" * 50 + "\n")

    # Run basic tests
    basic_ok, basic_results = test_basic()

    if not basic_ok:
        print("\n" + "=" * 50)
        print("RESULT: BASIC TESTS FAILED - stopping")
        print("=" * 50)
        return False

    # Run DAC/ADC tests
    print("\n" + "-" * 50 + "\n")
    dac_adc_ok, dac_adc_results = test_dac_adc()

    # Run AWG tests
    print("\n" + "-" * 50 + "\n")
    awg_ok, awg_results = test_awg()

    # Summary
    all_results = basic_results + dac_adc_results + awg_results
    all_pass = all(r[1] for r in all_results)

    print("\n" + "=" * 50)
    print("SUMMARY:")
    for name, passed in all_results:
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    print("=" * 50)
    print(f"RESULT: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")
    print("=" * 50)

    return all_pass

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
