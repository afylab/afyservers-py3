#!/usr/bin/env python3
"""
Trapezoid waveform test using AWG_WITH_ADC.
Waveform: 200us ramp up, 1000us plateau, 200us ramp down.
"""

import serial
import serial.tools.list_ports
import struct
import numpy as np
import matplotlib.pyplot as plt
import time

# Configuration
DAC_PORTS = [0]
ADC_PORTS = [0]  # 1 ADC channel
DAC_INTERVAL_US = 10   # 10us DAC interval
ADC_CONV_TIME_US = 100  # 100us ADC conversion time
NUM_CYCLES = 5

# Trapezoid timing
RAMP_UP_US = 225     # ramp
PLATEAU_US = 900     # plateau
RAMP_DOWN_US = 225   # ramp
TOTAL_PERIOD_US = RAMP_UP_US + PLATEAU_US + RAMP_DOWN_US  # 1400us

# Calculate steps for each phase (ensure at least 1 step each)
RAMP_UP_STEPS = max(1, RAMP_UP_US // DAC_INTERVAL_US)
PLATEAU_STEPS = max(1, PLATEAU_US // DAC_INTERVAL_US)
RAMP_DOWN_STEPS = max(1, RAMP_DOWN_US // DAC_INTERVAL_US)
NUM_DAC_STEPS = RAMP_UP_STEPS + PLATEAU_STEPS + RAMP_DOWN_STEPS


def find_port():
    for p in serial.tools.list_ports.comports():
        if 'usbmodem' in p.device:
            return p.device
    return '/dev/cu.usbmodem1301'


def generate_trapezoid(v_low, v_high):
    """Generate trapezoid waveform: ramp up, plateau, ramp down."""
    waveform = []

    # Ramp up (v_low to v_high)
    if RAMP_UP_STEPS == 1:
        waveform.append(v_high)  # Jump directly to high
    else:
        for i in range(RAMP_UP_STEPS):
            v = v_low + (v_high - v_low) * i / (RAMP_UP_STEPS - 1)
            waveform.append(v)

    # Plateau (hold at v_high)
    for i in range(PLATEAU_STEPS):
        waveform.append(v_high)

    # Ramp down (v_high to v_low)
    if RAMP_DOWN_STEPS == 1:
        waveform.append(v_low)  # Jump directly to low
    else:
        for i in range(RAMP_DOWN_STEPS):
            v = v_high - (v_high - v_low) * i / (RAMP_DOWN_STEPS - 1)
            waveform.append(v)

    return waveform


def generate_waveforms():
    """Generate trapezoid waveforms for each DAC channel."""
    waveforms = []
    # Different voltage ranges for each channel
    ranges = [(0.0, 4.0), (1.0, 3.0), (2.0, 5.0)]
    for i, port in enumerate(DAC_PORTS):
        v_low, v_high = ranges[i % len(ranges)]
        waveforms.append(generate_trapezoid(v_low, v_high))
    return waveforms


def send_cmd(ser, cmd, timeout=0.3):
    ser.reset_input_buffer()
    ser.write(f"{cmd}\r\n".encode())
    ser.flush()
    time.sleep(timeout)
    return ser.read(ser.in_waiting).decode('utf-8', errors='ignore').strip()


def main():
    VOLTAGE_LISTS = generate_waveforms()

    print(f"Trapezoid waveform parameters:")
    print(f"  Ramp up: {RAMP_UP_US}us ({RAMP_UP_STEPS} steps)")
    print(f"  Plateau: {PLATEAU_US}us ({PLATEAU_STEPS} steps)")
    print(f"  Ramp down: {RAMP_DOWN_US}us ({RAMP_DOWN_STEPS} steps)")
    print(f"  Total period: {TOTAL_PERIOD_US}us ({NUM_DAC_STEPS} steps)")
    print(f"  DAC interval: {DAC_INTERVAL_US}us")
    print(f"  Number of cycles: {NUM_CYCLES}")
    print()

    port = find_port()
    print(f"Using {port}")

    ser = serial.Serial(port, 115200, timeout=0.5)
    time.sleep(0.3)

    # Stop and init
    ser.write(b"STOP\r\n")
    time.sleep(0.2)
    ser.reset_input_buffer()

    resp = send_cmd(ser, "INITIALIZE", 0.5)
    print(f"Init: {resp[:50]}..." if len(resp) > 50 else f"Init: {resp}")

    # Set conversion time
    actual_conv = ADC_CONV_TIME_US
    for ch in ADC_PORTS:
        resp = send_cmd(ser, f"CONVERT_TIME,{ch},{ADC_CONV_TIME_US}", 0.2)
        try:
            actual_conv = float(resp)
        except:
            pass
    print(f"ADC conv time: {actual_conv:.1f}us")

    # Calculate expected data
    total_dac_time = NUM_DAC_STEPS * NUM_CYCLES * DAC_INTERVAL_US
    expected_adc_readings = int(total_dac_time / actual_conv)
    print(f"Expected ADC readings: ~{expected_adc_readings}")

    # Build command
    dacN = len(DAC_PORTS)
    adcN = len(ADC_PORTS)
    sdac = ",".join(str(p) for p in DAC_PORTS)
    sadc = ",".join(str(p) for p in ADC_PORTS)
    svolt = ",".join(f"{v:.4f}" for ch in VOLTAGE_LISTS for v in ch)
    cmd = f"AWG_WITH_ADC,{dacN},{adcN},{NUM_DAC_STEPS},{DAC_INTERVAL_US},{NUM_CYCLES},{sdac},{sadc},{svolt}"

    print(f"\nRunning AWG trapezoid waveform...")
    ser.reset_input_buffer()
    ser.write(f"{cmd}\r\n".encode())
    ser.flush()

    # Collect data - wait for all expected bytes or timeout
    expected_bytes = expected_adc_readings * adcN * 4
    data = b''
    # Wait for firmware to complete plus margin for serial transfer
    awg_duration_s = (total_dac_time / 1_000_000)
    timeout_end = time.time() + awg_duration_s + 1.0

    print(f"AWG duration: {awg_duration_s*1000:.1f}ms, expecting {expected_bytes} bytes...")

    while len(data) < expected_bytes and time.time() < timeout_end:
        if ser.in_waiting > 0:
            data += ser.read(ser.in_waiting)
        time.sleep(0.005)

    # Give extra time to drain any remaining data
    time.sleep(0.2)
    while ser.in_waiting > 0:
        data += ser.read(ser.in_waiting)
        time.sleep(0.01)

    # Stop (should already be stopped after numCycles)
    ser.write(b"STOP\r\n")
    time.sleep(0.1)

    # Reset DACs
    for p in DAC_PORTS:
        send_cmd(ser, f"SET,{p},0.0", 0.1)
    ser.close()

    # Parse data - check for error messages first
    if data.startswith(b'FAILURE') or data.startswith(b'ERROR'):
        print(f"Error from device: {data.decode('utf-8', errors='ignore')}")
        ser.close()
        return

    # Ensure data is aligned to 4-byte floats
    bytes_per_sample = adcN * 4
    data = data[:len(data) - (len(data) % bytes_per_sample)]  # Trim to alignment

    num_readings = len(data) // bytes_per_sample
    print(f"\nCollected {num_readings} ADC readings ({len(data)} bytes)")

    adc_data = {port: [] for port in ADC_PORTS}
    for i in range(num_readings):
        for j, port in enumerate(ADC_PORTS):
            offset = i * bytes_per_sample + j * 4
            v = struct.unpack('<f', data[offset:offset+4])[0]
            # Sanity check - ADC values should be -10 to +10V
            if -15 < v < 15:
                adc_data[port].append(v)
            else:
                adc_data[port].append(np.nan)  # Mark bad values

    # Time axes - ADC samples during the DAC waveform, spread evenly across total duration
    adc_sample_time = total_dac_time / num_readings  # Actual time between samples
    adc_time = (np.arange(num_readings) + 0.5) * adc_sample_time

    # DAC staircase for reference
    total_dac_steps = NUM_DAC_STEPS * NUM_CYCLES
    dac_time = []
    dac_values = [[] for _ in range(len(DAC_PORTS))]
    for step in range(total_dac_steps):
        t_start = step * DAC_INTERVAL_US
        t_end = (step + 1) * DAC_INTERVAL_US
        step_idx = step % NUM_DAC_STEPS
        dac_time.extend([t_start, t_end])
        for ch in range(len(DAC_PORTS)):
            dac_values[ch].extend([VOLTAGE_LISTS[ch][step_idx]] * 2)

    # Plot
    num_ch = len(ADC_PORTS)
    fig, axes = plt.subplots(num_ch, 1, figsize=(14, 4*num_ch), sharex=True)
    if num_ch == 1:
        axes = [axes]
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c']

    for i, port in enumerate(ADC_PORTS):
        ax = axes[i]
        # DAC reference (use first DAC channel for all ADC plots)
        dac_idx = min(i, len(DAC_PORTS) - 1)
        ax.plot(dac_time, dac_values[dac_idx], 'k-', lw=1.5, alpha=0.5, label=f'DAC {DAC_PORTS[dac_idx]}')
        # ADC readings
        ax.scatter(adc_time[:len(adc_data[port])], adc_data[port],
                   c=colors[i % 3], s=20, zorder=5, label=f'ADC {port}', alpha=0.7)
        ax.plot(adc_time[:len(adc_data[port])], adc_data[port],
                colors[i % 3], lw=1, alpha=0.5)

        ax.set_ylabel(f'Ch {port} (V)')
        ax.set_ylim(-12, 6)  # Show full ADC range
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right')

        # Print some values
        print(f"\nADC {port} first 10 values: {[f'{v:.2f}' for v in adc_data[port][:10]]}")

    axes[-1].set_xlabel('Time (us)')
    axes[-1].set_xlim(0, total_dac_time * 1.05)  # Focus on actual waveform duration
    axes[0].set_title(f'Trapezoid AWG: {RAMP_UP_US}us up, {PLATEAU_US}us plateau, {RAMP_DOWN_US}us down | {NUM_CYCLES} cycles')

    plt.tight_layout()
    plt.savefig('awg_trapezoid.png', dpi=150)
    plt.close()
    print(f"\nPlot saved to awg_trapezoid.png")


if __name__ == "__main__":
    main()
