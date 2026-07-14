from datetime import datetime
from pathlib import Path

import h5py
import numpy as np

from dac_adc_giga import dac_led_buffer_ramp_2d_with_callback
from labrad.wrappers import connectAsync
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

# Sweep configuration --------------------------------------------------------
DAC_PORTS = [4, 5]
ADC_PORTS = [6, 7]
START_POINT = [0.0, 0.0]
FAST_AXIS_VECTOR = [3.0, 2.0]
SLOW_AXIS_VECTOR = [2.0, 5.0]
STEPS_FAST = 500
STEPS_SLOW = 50

NUM_DAC_CHANNELS = len(DAC_PORTS)
NUM_ADC_CHANNELS = len(ADC_PORTS)

OUTDIR = Path("data")
OUTDIR.mkdir(exist_ok=True)

FILENAME = OUTDIR / f"{datetime.now():%Y%m%d_%H%M%S}_example_callback.h5"
FILE = h5py.File(FILENAME, "w")
COLUMN_NAMES = (
    ["ix", "iy"]
    + [f"DAC {p} [V]" for p in DAC_PORTS]
    + [f"ADC {p} [V]" for p in ADC_PORTS]
)
DATA = FILE.create_dataset(
    "data",
    shape=(0, len(COLUMN_NAMES)),
    maxshape=(None, len(COLUMN_NAMES)),
    dtype=np.float64,
    chunks=True,
)
DATA.attrs["column_names"] = COLUMN_NAMES
DATA.attrs["dac_ports"] = DAC_PORTS
DATA.attrs["adc_ports"] = ADC_PORTS
DATA.attrs["start_point"] = START_POINT
DATA.attrs["fast_axis_vector"] = FAST_AXIS_VECTOR
DATA.attrs["slow_axis_vector"] = SLOW_AXIS_VECTOR
ROWS_WRITTEN = 0

def line_handler(line_data: dict):
    """
    Save a single line of ramp data to the HDF5 file.
    """
    line_index = line_data["line_index"]
    channels = line_data.get("channels", [])
    length = max(len(ch) for ch in channels) if channels else 0
    if length == 0:
        return

    point_idx = np.arange(length, dtype=float)
    line_idx_col = np.full(length, float(line_index), dtype=float)

    slow_position = np.asarray(line_data["slow_position"], dtype=float)
    fast_axis = np.asarray(line_data["fast_axis_vector"], dtype=float)

    fast_fraction = np.linspace(0.0, 1.0, length)
    if line_data.get("fast_direction", "forward") == "backward":
        fast_fraction = fast_fraction[::-1]

    dac_samples = slow_position[None, :] + fast_fraction[:, None] * fast_axis

    adc_samples = np.full((length, NUM_ADC_CHANNELS), np.nan, dtype=float)
    for idx in range(min(NUM_ADC_CHANNELS, len(channels))):
        arr = np.asarray(channels[idx], dtype=float)
        count = min(len(arr), length)
        adc_samples[:count, idx] = arr[:count]

    rows = np.column_stack([point_idx, line_idx_col, dac_samples, adc_samples])

    global ROWS_WRITTEN
    start = ROWS_WRITTEN
    stop = start + rows.shape[0]
    DATA.resize((stop, DATA.shape[1]))
    DATA[start:stop, :] = rows
    ROWS_WRITTEN = stop

@inlineCallbacks
def main():
    cxn = yield connectAsync()
    server = cxn.dac_adc_giga
    yield server.select_device()

    try:
        yield dac_led_buffer_ramp_2d_with_callback(
            server,
            dacPorts=DAC_PORTS,
            adcPorts=ADC_PORTS,
            startPoint=START_POINT,
            fastAxisVector=FAST_AXIS_VECTOR,
            slowAxisVector=SLOW_AXIS_VECTOR,
            stepsFast=STEPS_FAST,
            stepsSlow=STEPS_SLOW,
            retrace=False,
            snake=False,
            numAdcAverages=1,
            dacInterval_us=500.0,
            dacSettlingTime_us=100.0,
            line_callback=line_handler,
        )
    finally:
        FILE.flush()
        FILE.close()
        yield cxn.disconnect()
        print(f"Saved {ROWS_WRITTEN} rows to {FILENAME}")
        reactor.stop()


if __name__ == "__main__":
    reactor.callWhenRunning(main)
    reactor.run()

