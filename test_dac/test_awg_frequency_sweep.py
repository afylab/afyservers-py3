#!/usr/bin/env python3
"""
Frequency sweep test for AWG_WITH_ADC to find glitch thresholds.
Tests 1, 2, and 3 ADC channels at various DAC intervals.
"""

import serial
import serial.tools.list_ports
import struct
import numpy as np
import time
import sys

def find_port():
    for p in serial.tools.list_ports.comports():
        if 'usbmodem' in p.device:
            return p.device
    return '/dev/cu.usbmodem1301'

def send_cmd(ser, cmd, timeout=0.3):
    ser.reset_input_buffer()
    ser.write(f"{cmd}\r\n".encode())
    ser.flush()
    time.sleep(timeout)
    return ser.read(ser.in_waiting).decode('utf-8', errors='ignore').strip()

def test_awg_with_adc(ser, dac_interval_us, num_adc_channels, num_cycles=3, verbose=False):
    """
    Run AWG_WITH_ADC test and check for glitches.
    Returns (success, num_readings, glitch_count, error_msg)
    """
    DAC_PORTS = [0]
    ADC_PORTS = list(range(num_adc_channels))
    NUM_DAC_STEPS = 30  # Simple ramp up/down

    # Generate simple triangle waveform
    voltages = []
    for i in range(NUM_DAC_STEPS):
        if i < NUM_DAC_STEPS // 2:
            v = 0.0 + (5.0 - 0.0) * i / (NUM_DAC_STEPS // 2 - 1)
        else:
            v = 5.0 - (5.0 - 0.0) * (i - NUM_DAC_STEPS // 2) / (NUM_DAC_STEPS // 2 - 1)
        voltages.append(v)

    # Build command
    dacN = len(DAC_PORTS)
    adcN = len(ADC_PORTS)
    sdac = ",".join(str(p) for p in DAC_PORTS)
    sadc = ",".join(str(p) for p in ADC_PORTS)
    svolt = ",".join(f"{v:.4f}" for v in voltages)
    cmd = f"AWG_WITH_ADC,{dacN},{adcN},{NUM_DAC_STEPS},{dac_interval_us},{num_cycles},{sdac},{sadc},{svolt}"

    # Calculate expected readings (approximate)
    adc_conv_time = 82  # ~82us per conversion for fast mode
    total_dac_time = NUM_DAC_STEPS * num_cycles * dac_interval_us
    expected_readings = int(total_dac_time / (adc_conv_time * num_adc_channels))

    # Send command
    ser.reset_input_buffer()
    ser.write(f"{cmd}\r\n".encode())
    ser.flush()

    # Collect data
    expected_bytes = expected_readings * adcN * 4
    data = b''
    awg_duration_s = total_dac_time / 1_000_000
    timeout_end = time.time() + awg_duration_s + 2.0

    while len(data) < expected_bytes and time.time() < timeout_end:
        if ser.in_waiting > 0:
            data += ser.read(ser.in_waiting)
        time.sleep(0.005)

    # Drain remaining
    time.sleep(0.1)
    while ser.in_waiting > 0:
        data += ser.read(ser.in_waiting)
        time.sleep(0.01)

    # Check for error messages
    if data.startswith(b'FAILURE') or data.startswith(b'ERROR'):
        return (False, 0, 0, data.decode('utf-8', errors='ignore')[:50])

    # Parse data
    bytes_per_sample = adcN * 4
    if len(data) < bytes_per_sample:
        return (False, 0, 0, "No data received")

    data = data[:len(data) - (len(data) % bytes_per_sample)]
    num_readings = len(data) // bytes_per_sample

    # Extract ADC values and check for glitches
    glitch_count = 0
    valid_values = []

    for i in range(num_readings):
        for j in range(adcN):
            offset = i * bytes_per_sample + j * 4
            v = struct.unpack('<f', data[offset:offset+4])[0]
            valid_values.append(v)
            # Check for obvious glitches (values way outside expected range)
            if v < -12 or v > 12:
                glitch_count += 1

    # Also check for sudden jumps (derivative check)
    if len(valid_values) > 1:
        for i in range(1, len(valid_values)):
            # If consecutive values from same channel differ by more than 3V, likely a glitch
            if i % adcN == (i-1) % adcN:  # Same channel
                if abs(valid_values[i] - valid_values[i-1]) > 4.0:
                    glitch_count += 1

    if verbose:
        print(f"    Got {num_readings} readings, {glitch_count} potential glitches")

    return (True, num_readings, glitch_count, "")

def check_device_responsive(ser):
    """Check if device responds to *IDN?"""
    ser.reset_input_buffer()
    ser.write(b"*IDN?\r\n")
    ser.flush()
    time.sleep(0.3)
    resp = ser.read(ser.in_waiting).decode('utf-8', errors='ignore').strip()
    return len(resp) > 0

def main():
    port = find_port()
    print(f"Using port: {port}")
    print("=" * 70)
    print("AWG_WITH_ADC Frequency Sweep Test")
    print("Finding glitch threshold for 1, 2, and 3 ADC channels")
    print("=" * 70)

    ser = serial.Serial(port, 115200, timeout=0.5)
    time.sleep(0.3)

    # Initialize
    ser.write(b"STOP\r\n")
    time.sleep(0.2)
    ser.reset_input_buffer()

    resp = send_cmd(ser, "INITIALIZE", 0.5)
    if "COMPLETE" not in resp and "INIT" not in resp.upper():
        print(f"Init failed: {resp}")
        ser.close()
        return
    print("Initialized successfully\n")

    # Test intervals from slow to fast
    # Start conservative and decrease until we see problems
    test_intervals = [100, 50, 40, 30, 25, 20, 15, 12, 10, 8, 6, 5, 4, 3, 2]

    results = {}

    for num_adc in [1, 2, 3]:
        print(f"\n{'='*60}")
        print(f"Testing with {num_adc} ADC channel(s)")
        print(f"{'='*60}")

        # Set fast conversion time
        for ch in range(num_adc):
            send_cmd(ser, f"CONVERT_TIME,{ch},82", 0.2)

        results[num_adc] = {'threshold': None, 'all_results': []}
        threshold_found = False

        for interval in test_intervals:
            # Check device is still responsive
            if not check_device_responsive(ser):
                print(f"  {interval:3d}us: DEVICE FROZEN - reinitializing...")
                ser.close()
                time.sleep(1)
                ser = serial.Serial(port, 115200, timeout=0.5)
                time.sleep(0.3)
                send_cmd(ser, "STOP", 0.2)
                send_cmd(ser, "INITIALIZE", 0.5)
                for ch in range(num_adc):
                    send_cmd(ser, f"CONVERT_TIME,{ch},82", 0.2)
                results[num_adc]['all_results'].append((interval, 'FROZEN'))
                if not threshold_found:
                    results[num_adc]['threshold'] = interval
                    threshold_found = True
                continue

            # Run test
            success, num_readings, glitches, err = test_awg_with_adc(
                ser, interval, num_adc, num_cycles=3, verbose=False
            )

            if not success:
                status = f"FAIL: {err}"
                results[num_adc]['all_results'].append((interval, 'FAIL'))
                if not threshold_found:
                    results[num_adc]['threshold'] = interval
                    threshold_found = True
            elif glitches > 5:  # Allow a few glitches as noise
                status = f"GLITCHY ({glitches} glitches in {num_readings} readings)"
                results[num_adc]['all_results'].append((interval, 'GLITCHY'))
                if not threshold_found:
                    results[num_adc]['threshold'] = interval
                    threshold_found = True
            else:
                status = f"OK ({num_readings} readings, {glitches} glitches)"
                results[num_adc]['all_results'].append((interval, 'OK'))

            freq_khz = 1000 / interval
            print(f"  {interval:3d}us ({freq_khz:5.1f} kHz): {status}")

            # Reset DAC
            send_cmd(ser, "SET,0,0.0", 0.1)
            time.sleep(0.05)

        if results[num_adc]['threshold'] is None:
            results[num_adc]['threshold'] = f"<{test_intervals[-1]}"

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for num_adc in [1, 2, 3]:
        threshold = results[num_adc]['threshold']
        if threshold is None:
            threshold_str = f"< {test_intervals[-1]}us (all passed)"
        elif isinstance(threshold, str):
            threshold_str = threshold
        else:
            freq_khz = 1000 / threshold
            threshold_str = f"{threshold}us ({freq_khz:.1f} kHz)"
        print(f"  {num_adc} ADC channel(s): glitch threshold at {threshold_str}")

    ser.close()
    print("\nDone!")

if __name__ == "__main__":
    main()
