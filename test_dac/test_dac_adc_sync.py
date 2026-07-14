#!/usr/bin/env python3
"""Test DAC->ADC synchronization: set DAC, immediately read ADC."""

import serial
import time
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

def test_single_dac_adc_sync():
    """Test: Set DAC0, then immediately read ADC0. They should match."""
    print("=" * 60)
    print("Test: Single DAC->ADC Synchronization")
    print("DAC0 and ADC0 are connected, so they should match")
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

        # Test voltages
        test_voltages = [-5.0, -2.5, 0.0, 2.5, 5.0]
        all_passed = True

        print(f"\n{'DAC Set':>10} {'ADC Read':>10} {'Error':>10} {'Status':>8}")
        print("-" * 45)

        for v in test_voltages:
            # Set DAC0
            response = send_command(ser, f"SET,0,{v}", 0.1)

            # Small delay for settling
            time.sleep(0.001)  # 1ms settling

            # Read ADC0
            response = send_command(ser, "GET_ADC,0", 0.1)
            try:
                adc_v = float(response)
                error = adc_v - v
                passed = abs(error) < 0.05  # 50mV tolerance
                status = "PASS" if passed else "FAIL"
                if not passed:
                    all_passed = False
                print(f"{v:>10.4f} {adc_v:>10.4f} {error:>10.4f} {status:>8}")
            except:
                print(f"{v:>10.4f} {'ERROR':>10} {'N/A':>10} {'FAIL':>8}")
                all_passed = False

        # Cleanup
        send_command(ser, "SET,0,0.0", 0.1)
        ser.close()

        print("-" * 45)
        print(f"Result: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
        return all_passed

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print(f"Using port: {PORT}\n")
    return test_single_dac_adc_sync()

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
