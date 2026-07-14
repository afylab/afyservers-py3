#!/usr/bin/env python3
"""
Simple AWG test - 100us DAC interval, 500us ADC conversion.
Saves data and plots result.
"""

import serial
import serial.tools.list_ports
import struct
import numpy as np
import matplotlib.pyplot as plt
import time

# Configuration
DAC_PORTS = [0, 1, 2]
ADC_PORTS = [0, 1, 2]
DAC_INTERVAL_US = 100
NUM_DAC_STEPS = 10  # 1000us period
ADC_CONV_TIME_US = 500
NUM_CYCLES = 10  # 10ms of data

def find_port():
    for p in serial.tools.list_ports.comports():
        if 'usbmodem' in p.device:
            return p.device
    return '/dev/cu.usbmodem1301'

def generate_waveforms():
    t = np.linspace(0, 2 * np.pi, NUM_DAC_STEPS, endpoint=False)
    ch0 = 2.5 + 2.5 * np.sin(t)  # Sine
    ch1 = 5.0 * np.abs(2 * (t / (2 * np.pi) - np.floor(t / (2 * np.pi) + 0.5)))  # Triangle
    ch2 = np.where(t < np.pi, 4.0, 1.0)  # Square
    return [ch0.tolist(), ch1.tolist(), ch2.tolist()]

def send_cmd(ser, cmd, timeout=0.3):
    ser.reset_input_buffer()
    ser.write(f"{cmd}\r\n".encode())
    ser.flush()
    time.sleep(timeout)
    return ser.read(ser.in_waiting).decode('utf-8', errors='ignore').strip()

def main():
    VOLTAGE_LISTS = generate_waveforms()

    port = find_port()
    print(f"Using {port}")

    ser = serial.Serial(port, 115200, timeout=0.5)
    time.sleep(0.3)

    # Stop and init
    ser.write(b"STOP\r\n")
    time.sleep(0.2)
    ser.reset_input_buffer()

    resp = send_cmd(ser, "INITIALIZE", 0.5)
    print(f"Init: {resp}")

    # Set conversion time to 500us
    actual_conv = ADC_CONV_TIME_US
    for ch in ADC_PORTS:
        resp = send_cmd(ser, f"CONVERT_TIME,{ch},{ADC_CONV_TIME_US}", 0.2)
        try:
            actual_conv = float(resp)
            print(f"ADC {ch} conv time: {actual_conv:.1f}us")
        except:
            print(f"ADC {ch} response: {resp}")

    # Calculate expected data
    total_dac_time = NUM_DAC_STEPS * NUM_CYCLES * DAC_INTERVAL_US
    expected_adc_readings = int(total_dac_time / actual_conv)
    print(f"\nDAC: {NUM_DAC_STEPS} steps @ {DAC_INTERVAL_US}us = {NUM_DAC_STEPS * DAC_INTERVAL_US}us period")
    print(f"Total time: {total_dac_time}us ({NUM_CYCLES} cycles)")
    print(f"Expected ADC readings: {expected_adc_readings}")

    # Build command
    dacN = len(DAC_PORTS)
    adcN = len(ADC_PORTS)
    sdac = ",".join(str(p) for p in DAC_PORTS)
    sadc = ",".join(str(p) for p in ADC_PORTS)
    svolt = ",".join(f"{v:.4f}" for ch in VOLTAGE_LISTS for v in ch)
    cmd = f"AWG_WITH_ADC,{dacN},{adcN},{NUM_DAC_STEPS},{DAC_INTERVAL_US},{sdac},{sadc},{svolt}"

    print(f"\nRunning AWG...")
    ser.reset_input_buffer()
    ser.write(f"{cmd}\r\n".encode())
    ser.flush()

    # Collect data
    expected_bytes = expected_adc_readings * adcN * 4
    data = b''
    timeout_end = time.time() + (total_dac_time / 1_000_000) + 2.0

    while len(data) < expected_bytes and time.time() < timeout_end:
        if ser.in_waiting > 0:
            data += ser.read(min(ser.in_waiting, expected_bytes - len(data)))
        time.sleep(0.001)

    # Stop
    ser.write(b"STOP\r\n")
    time.sleep(0.1)

    # Reset DACs
    for p in DAC_PORTS:
        send_cmd(ser, f"SET,{p},0.0", 0.1)
    ser.close()

    # Parse data
    num_readings = len(data) // (adcN * 4)
    print(f"\nCollected {num_readings} ADC readings ({len(data)} bytes)")

    adc_data = {port: [] for port in ADC_PORTS}
    for i in range(num_readings):
        for j, port in enumerate(ADC_PORTS):
            offset = i * adcN * 4 + j * 4
            v = struct.unpack('<f', data[offset:offset+4])[0]
            adc_data[port].append(v)

    # Time axes
    adc_time = (np.arange(num_readings) + 1) * actual_conv  # ADC completes at end of conversion

    # DAC staircase
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
        # DAC reference
        ax.plot(dac_time, dac_values[i], 'k-', lw=1.5, alpha=0.5, label=f'DAC {DAC_PORTS[i]}')
        # ADC readings
        ax.scatter(adc_time[:len(adc_data[port])], adc_data[port],
                   c=colors[i % 3], s=30, zorder=5, label=f'ADC {port}')
        ax.plot(adc_time[:len(adc_data[port])], adc_data[port],
                colors[i % 3], lw=1, alpha=0.5)

        ax.set_ylabel(f'Ch {port} (V)')
        ax.set_ylim(-0.5, 5.5)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right')

        # Print some values
        print(f"\nADC {port} first 10 values: {[f'{v:.2f}' for v in adc_data[port][:10]]}")

    axes[-1].set_xlabel('Time (us)')
    axes[0].set_title(f'AWG Test: DAC {DAC_INTERVAL_US}us interval, ADC {actual_conv:.0f}us conversion')

    plt.tight_layout()
    plt.savefig('/Users/space/Desktop/afyservers-py3/awg_test_500us.png', dpi=150)
    print(f"\nPlot saved to awg_test_500us.png")
    plt.show()

if __name__ == "__main__":
    main()
