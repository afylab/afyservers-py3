"""
dmm_stability_log.py
--------------------
Sets DAC channel 0 to 100 mV, then reads the Agilent 34401A DMM at 7.5-digit
resolution (100 NPLC) for 60 seconds.  Data are saved to a tab-delimited text
file and a PNG plot is produced.

Usage:
    python dmm_stability_log.py

Optional CLI overrides:
    --dac-port     DAC output channel (default 0)
    --dac-voltage  DAC set-point in volts (default 0.1)
    --duration     Measurement duration in seconds (default 60)
    --nplc         DMM integration time in power-line cycles (default 100)
    --out          Output file stem, no extension (default: timestamped)
    --dac-device   DAC device index for select_device (default 0)
    --dmm-device   DMM device index for select_device (default 0)
"""

import argparse
import time
from datetime import datetime
from pathlib import Path

import labrad
import matplotlib
matplotlib.use("Agg")          # non-interactive backend; works headless
import matplotlib.pyplot as plt
import numpy as np


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dac-port",    type=int,   default=0,    help="DAC output channel (0–7)")
    p.add_argument("--dac-voltage", type=float, default=0.1,  help="DAC set-point in volts")
    p.add_argument("--duration",    type=float, default=60.0, help="Measurement duration (s)")
    p.add_argument("--dmm-range", type=float, default=0.1, help="imput range of DMM")
    p.add_argument("--dmm-res", type=float, default=1e-7, help="imput range of DMM")
    p.add_argument("--nplc",        type=int,   default=20,  help="DMM NPLC (100 → 7.5 digits)")
    p.add_argument("--out",         type=str,   default=None, help="Output file stem (no extension)")
    p.add_argument("--dac-device",  type=int,   default=0,    help="DAC server device index")
    p.add_argument("--dmm-device",  type=int,   default=0,    help="DMM server device index")
    p.add_argument("--keep-voltage", type=bool, default=False, help="do not set voltage")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    # ---- output paths -------------------------------------------------------
    if args.out is None:
        stem = datetime.now().strftime("%Y%m%d_%H%M%S") + "_dmm_stability"
    else:
        stem = args.out

    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    txt_path = out_dir / f"{stem}.txt"
    png_path = out_dir / f"{stem}.png"

    # ---- connect to LabRAD --------------------------------------------------
    print("Connecting to LabRAD manager…")
    with labrad.connect() as cxn:

        # -- DAC ----------------------------------------------------------------
        dac = cxn.dac_adc_giga
        dac.select_device(args.dac_device)

        kv = args.keep_voltage
        if not kv:
	        print(f"Setting DAC port {args.dac_port} to {args.dac_voltage * 1e3:.1f} mV…")
	        resp = dac.set_voltage(args.dac_port, args.dac_voltage)
	        print(f"  DAC response: {resp}")

        # Allow the output to settle
        time.sleep(0.5)

        # -- DMM ----------------------------------------------------------------
        dmm = cxn.agilent_34401a_dmm
        dmm.select_device(args.dmm_device)

        # Configure: 10 V range, NPLC = 100 (7.5-digit integration)
        print(f"Configuring DMM: DC voltage, 10 V range, {args.nplc} NPLC…")
        dmm_range = args.dmm_range
        dmm_res = args.dmm_res
        dmm.configure_voltage(dmm_range, dmm_res)   # 10 V range, 100 nV resolution field
        dmm.configure_nplc(args.nplc)

        # ---- acquisition loop -----------------------------------------------
        print(f"Logging for {args.duration:.0f} s — press Ctrl-C to abort early.\n")

        timestamps = []   # elapsed time in seconds
        voltages   = []   # measured voltage in volts

        t_start = time.monotonic()
        t_end   = t_start + args.duration
        sample  = 0

        with open(txt_path, "w") as f:
            # Header
            f.write(f"# DAC port {args.dac_port} set to {args.dac_voltage} V\n")
            f.write(f"# DMM: Agilent 34401A, {args.nplc} NPLC\n")
            f.write(f"# Start: {datetime.now().isoformat()}\n")
            f.write("# time_s\tvoltage_V\n")

            try:
                while time.monotonic() < t_end:
                    v = dmm.read_voltage()           # blocks for one integration period
                    t = time.monotonic() - t_start

                    timestamps.append(t)
                    voltages.append(float(v))
                    sample += 1

                    line = f"{t:.6f}\t{float(v):.9f}"
                    f.write(line + "\n")
                    f.flush()

                    print(f"  [{sample:4d}]  t = {t:7.2f} s   V = {float(v)*1e3:.6f} mV")

            except KeyboardInterrupt:
                print("\nAborted by user.")

    # ---- statistics ---------------------------------------------------------
    arr = np.array(voltages)
    print(f"\nSamples : {len(arr)}")
    print(f"Mean    : {arr.mean()*1e3:.6f} mV")
    print(f"Std dev : {arr.std()*1e6:.3f} µV  ({arr.std()/arr.mean()*1e6:.2f} ppm)")
    print(f"Peak–peak: {(arr.max()-arr.min())*1e6:.3f} µV")
    print(f"\nData saved → {txt_path}")

    # ---- plot ---------------------------------------------------------------
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), constrained_layout=True)

    # Top: raw trace
    ax = axes[0]
    ax.plot(timestamps, np.array(voltages) * 1e3, color="royalblue", lw=1.2)
    ax.axhline(arr.mean() * 1e3, color="firebrick", ls="--", lw=0.9, label=f"mean = {arr.mean()*1e3:.6f} mV")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Voltage (mV)")
    ax.set_title(f"DMM Stability — DAC port {args.dac_port} set to {args.dac_voltage*1e3:.1f} mV, {args.nplc} NPLC")
    ax.legend(fontsize=9)
    ax.grid(True, lw=0.4, alpha=0.5)

    # Bottom: deviation from mean in µV
    ax2 = axes[1]
    dev_uV = (arr - arr.mean()) * 1e6
    ax2.plot(timestamps, dev_uV, color="darkorange", lw=1.0)
    ax2.axhline(0, color="k", lw=0.6)
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Deviation from mean (µV)")
    ax2.set_title(f"σ = {arr.std()*1e6:.3f} µV   ({arr.std()/arr.mean()*1e6:.2f} ppm rms)")
    ax2.grid(True, lw=0.4, alpha=0.5)

    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    print(f"Plot saved  → {png_path}")


if __name__ == "__main__":
    main()