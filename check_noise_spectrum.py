"""
psd_measurement.py
------------------
Acquire two 2-minute ADC time series (background and signal) and compute
their power spectral densities via Welch's method, plus a simple
background-subtracted PSD.

Setup
-----
  Background : ADC channel 0 input shorted to ground
  Signal     : ADC channel 0 connected to DAC output at 50 mV
  ADC gain   : 100x  (set via hardware before running)
  Conversion : 2.602 ms  →  fs ≈ 384.7 Hz

Usage
-----
  python psd_measurement.py [--device 0] [--dac-port 0] [--duration 120]
"""

import argparse
import time

import labrad
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import welch

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ADC_CHANNEL   = 0
CONV_TIME_MS  = 2.602
CONV_TIME_US  = CONV_TIME_MS * 1e3
DURATION_S    = 120.0
TOTAL_TIME_US = DURATION_S * 1e6
ADC_GAIN      = 100
DAC_VOLTAGE_V = 0.050

WELCH_NPERSEG = 1024
WELCH_NOVERLAP = 512
WELCH_WINDOW  = 'hann'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def prompt(message):
    input(f"\n{'='*60}\n{message}\nPress Enter when ready...")
    print()


def acquire(server, label):
    print(f"[{label}] Acquiring {DURATION_S:.0f} s at {CONV_TIME_MS} ms conv time...")
    t0 = time.time()
    raw = server.time_series_adc_read([ADC_CHANNEL], CONV_TIME_US, TOTAL_TIME_US)
    elapsed = time.time() - t0
    data = np.asarray(raw[0], dtype=float)
    print(f"[{label}] {len(data)} samples in {elapsed:.1f} s  "
          f"(fs ≈ {len(data)/elapsed:.2f} Hz)")
    return data


def compute_psd(signal, fs):
    nperseg  = min(WELCH_NPERSEG, len(signal))
    noverlap = min(WELCH_NOVERLAP, nperseg // 2)
    return welch(signal, fs=fs, window=WELCH_WINDOW,
                 nperseg=nperseg, noverlap=noverlap, scaling='density')


def plot_results(freq, psd_bg, psd_sig, psd_sub, fs, n_bg, n_sig):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(
        f"ADC Ch{ADC_CHANNEL}  |  Gain {ADC_GAIN}×  |  "
        f"$f_s$ ≈ {fs:.1f} Hz  |  "
        f"$N_\\mathrm{{bg}}$={n_bg}, $N_\\mathrm{{sig}}$={n_sig}",
        fontsize=12,
    )
    for ax, xscale, title in [
        (axes[0], 'linear', 'PSD — linear frequency'),
        (axes[1], 'log',    'PSD — log–log'),
    ]:
        mask = freq > 0 if xscale == 'log' else np.ones(len(freq), dtype=bool)
        ax.plot(freq[mask], psd_bg[mask],  color='steelblue',  lw=1.2,
                label='Background (shorted)')
        ax.plot(freq[mask], psd_sig[mask], color='darkorange',  lw=1.2,
                label=f'Signal (DAC = {DAC_VOLTAGE_V*1e3:.0f} mV)')
        ax.plot(freq[mask], psd_sub[mask], color='seagreen',    lw=1.2,
                ls='--', label='Signal − Background')
        ax.set_xlabel('Frequency (Hz)')
        ax.set_ylabel('PSD (V² / Hz)')
        ax.set_xscale(xscale)
        ax.set_yscale('log')
        ax.set_title(title)
        ax.legend(fontsize=9)
        ax.grid(True, which='both', alpha=0.3)
    plt.tight_layout()
    fig.savefig('psd_results.png', dpi=150)
    print("Figure saved → psd_results.png")
    plt.show()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--device',   type=int, default=0)
    parser.add_argument('--dac-port', type=int, default=0)
    parser.add_argument('--duration', type=float, default=120)
    args = parser.parse_args()

    DURATION_S    = args.duration
    TOTAL_TIME_US = DURATION_S * 1e6

    print("=" * 60)
    print(f"  PSD Measurement  |  ADC ch {ADC_CHANNEL}  |  gain {ADC_GAIN}x  |  "
          f"conv {CONV_TIME_MS} ms  |  {DURATION_S:.0f} s")
    print("=" * 60)

    with labrad.connect() as cxn:
        server = cxn.dac_adc_giga
        server.select_device(args.device)

        # Set conversion time and read back the actual value
        actual_conv_us = server.set_conversionTime(ADC_CHANNEL, CONV_TIME_US)
        fs = 1.0 / (actual_conv_us * 1e-6)
        print(f"Conversion time confirmed: {actual_conv_us/1e3:.4f} ms  →  fs ≈ {fs:.2f} Hz")

        # --- Background ---
        prompt(
            "BACKGROUND\n"
            f"  1. Short ADC channel {ADC_CHANNEL} input to ground.\n"
            "  2. Confirm ADC hardware gain is set to 100x.\n"
            "  3. DAC should NOT be connected to the ADC."
        )
        data_bg = acquire(server, "Background")

        # --- Signal ---
        prompt(
            "SIGNAL\n"
            f"  1. Connect DAC port {args.dac_port} to ADC channel {ADC_CHANNEL}.\n"
            f"  2. Script will set DAC port {args.dac_port} to {DAC_VOLTAGE_V*1e3:.0f} mV.\n"
            "  3. ADC hardware gain remains at 100x."
        )
        server.set_voltage(args.dac_port, DAC_VOLTAGE_V)
        print(f"DAC port {args.dac_port} set to {DAC_VOLTAGE_V*1e3:.0f} mV.")
        data_sig = acquire(server, "Signal")
        server.set_voltage(args.dac_port, 0.0)
        print(f"DAC port {args.dac_port} returned to 0 V.")

    # --- PSD ---
    print("\nComputing PSDs...")
    freq, psd_bg  = compute_psd(data_bg,  fs)
    _,    psd_sig = compute_psd(data_sig, fs)
    psd_sub = np.clip(psd_sig - psd_bg, 0.0, None)

    print(f"  Background RMS : {np.std(data_bg)*1e6:.2f} µV at ADC input "
          f"({np.std(data_bg)/ADC_GAIN*1e6:.2f} µV referred to source)")
    print(f"  Signal RMS     : {np.std(data_sig)*1e6:.2f} µV at ADC input "
          f"({np.std(data_sig)/ADC_GAIN*1e6:.2f} µV referred to source)")

    # --- Save to text files ---
    # Time series: one column per dataset, header describes each
    ts_header = (
        f"ADC channel: {ADC_CHANNEL}  gain: {ADC_GAIN}x  "
        f"conv_time_us: {actual_conv_us:.4f}  fs_Hz: {fs:.4f}\n"
        "background_V  signal_V"
    )
    # Pad to equal length in case sample counts differ slightly
    n_max = max(len(data_bg), len(data_sig))
    ts_bg  = np.pad(data_bg,  (0, n_max - len(data_bg)),  constant_values=np.nan)
    ts_sig = np.pad(data_sig, (0, n_max - len(data_sig)), constant_values=np.nan)
    np.savetxt('time_series.txt', np.column_stack([ts_bg, ts_sig]),
               header=ts_header, fmt='%.8e')
    print("Time series saved → time_series.txt")

    # PSD: four columns — freq, psd_bg, psd_sig, psd_subtracted
    psd_header = (
        f"ADC channel: {ADC_CHANNEL}  gain: {ADC_GAIN}x  "
        f"conv_time_us: {actual_conv_us:.4f}  fs_Hz: {fs:.4f}  "
        f"dac_voltage_V: {DAC_VOLTAGE_V}\n"
        "freq_Hz  psd_bg_V2perHz  psd_sig_V2perHz  psd_subtracted_V2perHz"
    )
    np.savetxt('psd_data.txt', np.column_stack([freq, psd_bg, psd_sig, psd_sub]),
               header=psd_header, fmt='%.8e')
    print("PSD data saved → psd_data.txt")

    plot_results(freq, psd_bg, psd_sig, psd_sub, fs, len(data_bg), len(data_sig))


if __name__ == '__main__':
    main()