#!/usr/bin/env python3
"""Test AWG at fast intervals (10us, 25us, 50us) to check for glitches."""

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

def test_awg_interval(interval_us):
    """Test AWG with 2-point square wave at given interval."""
    print(f"\n{'='*60}")
    print(f"Testing AWG at {interval_us}us interval (2-point square wave)")
    print(f"{'='*60}")

    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.5)
        time.sleep(0.3)
        ser.reset_input_buffer()

        # Initialize
        response = send_command(ser, "INITIALIZE", 0.5)
        if "COMPLETE" not in response:
            print(f"  Init failed: {response}")
            ser.close()
            return False
        print("  Initialized")

        # AWG command: 1 DAC channel, 2 steps (0V and 5V), no ADC
        # AWG_BUFFER_RAMP,numDacChannels,numSteps,interval_us,dacChannel,v0,v1,...
        # Actually the format is: AWG_BUFFER_RAMP,numDacChannels,numAdcChannels,numLoops,numSteps,numAvgs,interval_us,dacCh,voltages...,adcCh
        cmd = f"AWG_BUFFER_RAMP,1,0,1,2,1,{interval_us},0,0.0,5.0"
        print(f"  Command: {cmd}")

        # Start AWG
        ser.reset_input_buffer()
        ser.write(f"{cmd}\r\n".encode())
        ser.flush()

        print(f"  AWG running at {interval_us}us ({1000000/interval_us/2:.1f} kHz square wave)")
        print(f"  Running for 2 seconds...")
        time.sleep(2)

        # Stop AWG
        response = send_command(ser, "STOP", 0.5)
        if "RAMPING_STOPPED" in response:
            print(f"  AWG stopped successfully")
        else:
            print(f"  Stop response: {response}")

        # Verify DAC still responds
        response = send_command(ser, "GET_DAC,0", 0.3)
        try:
            voltage = float(response)
            print(f"  DAC voltage after stop: {voltage:.4f}V")
            result = True
        except:
            print(f"  ERROR: GET_DAC failed: {response}")
            result = False

        # Cleanup
        send_command(ser, "SET,0,0.0", 0.2)
        ser.close()
        return result

    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("Fast AWG Interval Tests")
    print("=" * 60)
    print(f"Using port: {PORT}")

    # Test at different intervals
    intervals = [100, 50, 25, 10]
    results = {}

    for interval in intervals:
        results[interval] = test_awg_interval(interval)

    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("=" * 60)
    for interval, passed in results.items():
        status = "PASS" if passed else "FAIL"
        freq = 1000000 / interval / 2
        print(f"  {interval:3d}us ({freq:6.1f} kHz): {status}")

    all_passed = all(results.values())
    print("=" * 60)
    print(f"RESULT: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    print("=" * 60)

    return all_passed

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
