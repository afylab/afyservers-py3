#!/usr/bin/env python3
"""
Fast oscilloscope display - direct serial, no LabRAD overhead.
"""

import serial
import serial.tools.list_ports
import struct
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import threading
import time

# Configuration
DAC_PORTS = [0, 1, 2]
ADC_PORTS = [0, 1, 2]
DAC_INTERVAL_US = 100
NUM_DAC_STEPS = 10
ADC_CONV_TIME_US = 82
DISPLAY_WINDOW_US = 5000

READINGS_PER_FRAME = int(DISPLAY_WINDOW_US / ADC_CONV_TIME_US)

# Find serial port
def find_port():
    for p in serial.tools.list_ports.comports():
        if 'usbmodem' in p.device:
            return p.device
    return '/dev/cu.usbmodem1301'

# Generate waveforms
def generate_waveforms():
    t = np.linspace(0, 2 * np.pi, NUM_DAC_STEPS, endpoint=False)
    ch0 = 2.5 + 2.5 * np.sin(t)
    ch1 = 5.0 * np.abs(2 * (t / (2 * np.pi) - np.floor(t / (2 * np.pi) + 0.5)))
    ch2 = np.where(t < np.pi, 4.0, 1.0)
    return [ch0.tolist(), ch1.tolist(), ch2.tolist()]

VOLTAGE_LISTS = generate_waveforms()

# Pre-compute DAC staircase
dac_staircases = []
for i in range(3):
    dac_t, dac_v = [], []
    for step in range(int(DISPLAY_WINDOW_US / DAC_INTERVAL_US) + 1):
        t_start = step * DAC_INTERVAL_US
        t_end = (step + 1) * DAC_INTERVAL_US
        v = VOLTAGE_LISTS[i][step % NUM_DAC_STEPS]
        dac_t.extend([t_start, t_end])
        dac_v.extend([v, v])
    dac_staircases.append((dac_t, dac_v))

# Shared data
frame_data = {port: [] for port in ADC_PORTS}
frame_lock = threading.Lock()
running = True
frame_count = [0]
actual_conv_time = [ADC_CONV_TIME_US]

# Plot setup
plt.ion()
fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
colors = ['#1f77b4', '#ff7f0e', '#2ca02c']
lines = []

for i, (ax, port) in enumerate(zip(axes, ADC_PORTS)):
    ax.plot(dac_staircases[i][0], dac_staircases[i][1], 'k-', lw=1, alpha=0.4, label=f'DAC {DAC_PORTS[i]}')
    line, = ax.plot([], [], '-', color=colors[i], lw=1.5, label=f'ADC {port}')
    lines.append(line)
    ax.set_ylabel(f'Ch {port} (V)')
    ax.set_ylim(-0.5, 5.5)
    ax.set_xlim(0, DISPLAY_WINDOW_US)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper right', fontsize=8)

axes[-1].set_xlabel('Time (us)')
axes[0].set_title('AWG Oscilloscope')
plt.tight_layout()


def send_cmd(ser, cmd, timeout=0.3):
    ser.reset_input_buffer()
    ser.write(f"{cmd}\r\n".encode())
    ser.flush()
    time.sleep(timeout)
    return ser.read(ser.in_waiting).decode('utf-8', errors='ignore').strip()


def serial_reader(ser):
    global running
    adcN = len(ADC_PORTS)
    buffer = b''
    reading_idx = 0

    while running:
        # Read available data
        if ser.in_waiting > 0:
            buffer += ser.read(ser.in_waiting)

        # Process complete readings (each is adcN * 4 bytes)
        bytes_per_reading = adcN * 4
        while len(buffer) >= bytes_per_reading:
            chunk = buffer[:bytes_per_reading]
            buffer = buffer[bytes_per_reading:]

            values = []
            for i in range(adcN):
                v = struct.unpack('<f', chunk[i*4:(i+1)*4])[0]
                values.append(v)

            with frame_lock:
                for i, port in enumerate(ADC_PORTS):
                    frame_data[port].append(values[i])

            reading_idx += 1

        time.sleep(0.001)  # Small sleep to prevent CPU spin


def display_loop():
    global running
    while running:
        with frame_lock:
            # Check if we have a full frame
            if len(frame_data[ADC_PORTS[0]]) >= READINGS_PER_FRAME:
                # Display
                t_arr = np.arange(READINGS_PER_FRAME) * actual_conv_time[0]
                for i, port in enumerate(ADC_PORTS):
                    lines[i].set_data(t_arr, frame_data[port][:READINGS_PER_FRAME])

                frame_count[0] += 1
                axes[0].set_title(f'AWG Oscilloscope | Frame {frame_count[0]}')

                # Clear for next frame
                for port in ADC_PORTS:
                    frame_data[port] = frame_data[port][READINGS_PER_FRAME:]

        try:
            fig.canvas.draw_idle()
            fig.canvas.flush_events()
        except:
            break

        time.sleep(0.01)  # 100 Hz display update


def main():
    global running

    port = find_port()
    print(f"Using {port}")

    ser = serial.Serial(port, 115200, timeout=0.1)
    time.sleep(0.3)

    # Stop any running operation
    ser.write(b"STOP\r\n")
    time.sleep(0.2)
    ser.reset_input_buffer()

    # Initialize
    resp = send_cmd(ser, "INITIALIZE", 0.5)
    print(f"Init: {resp}")

    # Set conversion time
    for ch in ADC_PORTS:
        resp = send_cmd(ser, f"CONVERT_TIME,{ch},{ADC_CONV_TIME_US}", 0.2)
        try:
            actual_conv_time[0] = float(resp)
        except:
            pass
    print(f"ADC conv time: {actual_conv_time[0]:.0f}us")

    # Build AWG command
    dacN = len(DAC_PORTS)
    adcN = len(ADC_PORTS)
    sdac = ",".join(str(p) for p in DAC_PORTS)
    sadc = ",".join(str(p) for p in ADC_PORTS)
    svolt = ",".join(str(v) for ch in VOLTAGE_LISTS for v in ch)
    cmd = f"AWG_WITH_ADC,{dacN},{adcN},{NUM_DAC_STEPS},{DAC_INTERVAL_US},{sdac},{sadc},{svolt}"

    print(f"Starting AWG... Ctrl+C to stop")
    ser.reset_input_buffer()
    ser.write(f"{cmd}\r\n".encode())
    ser.flush()

    # Start reader thread
    reader_thread = threading.Thread(target=serial_reader, args=(ser,), daemon=True)
    reader_thread.start()

    # Display loop in main thread
    try:
        display_loop()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        running = False
        ser.write(b"STOP\r\n")
        time.sleep(0.1)
        for p in DAC_PORTS:
            send_cmd(ser, f"SET,{p},0.0", 0.1)
        ser.close()
        plt.close('all')


if __name__ == "__main__":
    main()
