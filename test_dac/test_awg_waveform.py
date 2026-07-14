#!/usr/bin/env python3
"""Test AWG_WITH_ADC with a complex waveform and plot DAC vs ADC."""

import serial
import time
import struct
import glob
import numpy as np
import matplotlib.pyplot as plt

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

def test_waveform():
    """Test AWG with a 10-step waveform repeated 10 times."""
    print(f"Using port: {PORT}")
    print("=" * 60)

    # Create trapezoid waveform: ramp up (4 pts), plateau (20 pts), ramp down (4 pts)
    ramp_points = 4
    plateau_points = 20
    num_steps = ramp_points + plateau_points + ramp_points  # 28 total
    num_cycles = 5
    interval_us = 100  # 100us spacing, ADC conversion ~500us will average ~5 points

    # Generate trapezoid: 0V -> 5V ramp, 5V plateau, 5V -> 0V ramp
    v_low, v_high = 0.0, 5.0
    ramp_up = np.linspace(v_low, v_high, ramp_points, endpoint=False)
    plateau = np.full(plateau_points, v_high)
    ramp_down = np.linspace(v_high, v_low, ramp_points, endpoint=False)
    waveform = np.concatenate([ramp_up, plateau, ramp_down])

    print(f"Waveform ({num_steps} steps):")
    print(f"  Values: {[f'{v:.2f}' for v in waveform]}")
    print(f"  Interval: {interval_us}us")
    print(f"  Cycles: {num_cycles}")
    print(f"  Total duration: {num_steps * num_cycles * interval_us / 1000:.1f}ms")
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
            return
        print("Initialized")

        # Set ADC conversion time
        requested_conversion_time_us = 500
        response = send_command(ser, f"CONVERT_TIME,0,{requested_conversion_time_us}", 0.3)
        # Parse actual conversion time from response
        try:
            conversion_time_us = float(response)
        except:
            conversion_time_us = requested_conversion_time_us
        print(f"Set conversion time: {conversion_time_us}us")

        # Build command: AWG_WITH_ADC,dac_n,adc_n,num_steps,interval_us,dac_ch,adc_ch,v0,v1,...
        dac_ch = 0
        adc_ch = 0
        voltages_str = ",".join([f"{v:.4f}" for v in waveform])
        cmd = f"AWG_WITH_ADC,1,1,{num_steps},{interval_us},{dac_ch},{adc_ch},{voltages_str}"

        print(f"Command: {cmd[:80]}...")
        print("Running AWG...")

        # Send command
        ser.reset_input_buffer()
        ser.write(f"{cmd}\r\n".encode())
        ser.flush()

        # Calculate expected number of ADC readings
        total_dac_time_us = num_steps * num_cycles * interval_us
        expected_adc_readings = int(total_dac_time_us // conversion_time_us)
        expected_bytes = expected_adc_readings * 4  # 4 bytes per float

        print(f"Total DAC time: {total_dac_time_us}us")
        print(f"Expected ADC readings: {expected_adc_readings}")

        # Collect exactly the expected number of ADC readings
        adc_data = b''
        timeout_s = (total_dac_time_us / 1_000_000) + 1.0  # DAC time + 1s timeout
        start_time = time.time()

        while len(adc_data) < expected_bytes and (time.time() - start_time) < timeout_s:
            chunk = ser.read(expected_bytes - len(adc_data))
            if chunk:
                adc_data += chunk

        # Stop AWG
        ser.write(b"STOP\r\n")
        ser.flush()
        time.sleep(0.1)
        ser.read(1000)

        # Cleanup
        send_command(ser, "SET,0,0.0", 0.1)
        ser.close()

        # Parse ADC readings
        num_floats = len(adc_data) // 4
        adc_readings = []
        for i in range(num_floats):
            value = struct.unpack('<f', adc_data[i*4:(i+1)*4])[0]
            adc_readings.append(value)

        print(f"Collected {num_floats} ADC readings (expected {expected_adc_readings})")

        if num_floats < expected_adc_readings:
            print("Not enough data collected!")
            return

        # Use exactly the expected number of readings
        adc_readings = adc_readings[:expected_adc_readings]

        # Total duration in ms
        total_time_ms = total_dac_time_us / 1000

        # ADC readings are spaced by conversion_time_us
        # First reading completes at conversion_time_us, not at 0
        adc_time = (np.arange(len(adc_readings)) + 1) * conversion_time_us / 1000  # in ms

        # DAC waveform: each step lasts interval_us
        # Create staircase showing actual DAC output over time
        dac_time = []
        dac_values = []
        total_dac_steps = num_steps * num_cycles
        for i in range(total_dac_steps):
            step_idx = i % num_steps
            t_start = i * interval_us / 1000
            t_end = (i + 1) * interval_us / 1000
            # Add point at start and end of each step for staircase
            dac_time.extend([t_start, t_end])
            dac_values.extend([waveform[step_idx], waveform[step_idx]])

        # Plot
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

        # Top plot: DAC output (line) and ADC readings (points)
        ax1.plot(dac_time, dac_values, 'b-', linewidth=1.5, label='DAC Output', alpha=0.7)
        ax1.scatter(adc_time, adc_readings, c='red', s=20, label='ADC Reading', zorder=5)
        ax1.set_ylabel('Voltage (V)')
        ax1.set_title(f'AWG_WITH_ADC: {num_steps}-step waveform, {num_cycles} cycles @ {interval_us}us interval')
        ax1.legend(loc='upper right')
        ax1.grid(True, alpha=0.3)
        ax1.set_ylim(-0.5, 5.5)

        # Bottom plot: Error (ADC - expected DAC)
        # For each ADC reading, find the DAC value at the time of that reading
        # ADC reading i integrates from i*conversion_time to (i+1)*conversion_time
        # Use midpoint for comparison
        errors = []
        for i, adc_val in enumerate(adc_readings):
            # ADC reading i integrates during this window, use midpoint
            adc_midpoint_us = (i + 0.5) * conversion_time_us
            # Which DAC step was active at that time?
            dac_step_idx = int(adc_midpoint_us // interval_us) % num_steps
            expected_dac = waveform[dac_step_idx]
            errors.append(adc_val - expected_dac)

        ax2.scatter(adc_time, errors, c='green', s=15, alpha=0.7)
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax2.axhline(y=0.1, color='red', linestyle='--', linewidth=0.5, alpha=0.5)
        ax2.axhline(y=-0.1, color='red', linestyle='--', linewidth=0.5, alpha=0.5)
        ax2.set_xlabel('Time (ms)')
        ax2.set_ylabel('Error (V)')
        ax2.set_title('ADC Error (ADC reading - expected DAC value)')
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(-0.5, 0.5)

        plt.tight_layout()

        # Save figure
        output_file = '/Users/space/Desktop/dac/dac-adc-firmware/m4/awg_waveform_test.png'
        plt.savefig(output_file, dpi=150)
        print(f"Plot saved to: {output_file}")

        # Statistics
        errors_arr = np.array(errors)
        print(f"\nStatistics:")
        print(f"  Mean error: {np.mean(errors_arr):.4f}V")
        print(f"  Std error:  {np.std(errors_arr):.4f}V")
        print(f"  Max error:  {np.max(np.abs(errors_arr)):.4f}V")
        print(f"  Within ±0.1V: {np.sum(np.abs(errors_arr) < 0.1)}/{len(errors_arr)} ({100*np.sum(np.abs(errors_arr) < 0.1)/len(errors_arr):.1f}%)")

        plt.show()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_waveform()
