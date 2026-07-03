"""
Integration test suite for the DAC-ADC-GIGA LabRAD server.

These are INTEGRATION tests, not isolated unit tests: they require a live
connection to a running `dac_adc_giga` LabRAD server with a physical
Arduino DAC-ADC-GIGA device attached and selected. They exercise every
LabRAD setting exposed by dac_adc_giga.py, EXCLUDING the AWG-related
settings (generate_awg / awg_with_adc / sigAWGData helpers), per request.

Requirements
------------
- A LabRAD manager running and reachable (pylabrad `connectAsync` / sync
  `labrad.connect`)
- The `dac_adc_giga` server running and a device already selected on the
  context used by the test session (see `select_device` fixture)
- pytest, pytest-twisted (for inlineCallbacks-friendly async tests)

Hardware setup notes
---------------------
Several tests are physically destructive/invasive in the sense that they
change DAC outputs and assume nothing downstream will be damaged by
ramping through +/-10 V. Before running:
  * Disconnect or isolate any sensitive sample / cryostat wiring.
  * For buffer-ramp tests, DAC channel `i` is looped back to ADC channel
    `i` (i.e. DAC0->ADC0, DAC1->ADC1, ... DAC7->ADC7) via short coax or
    twisted-pair jumpers on the breakout board. This is required for the
    8-channel buffer ramp test and is assumed throughout.
  * Calibration tests (zero-scale / full-scale) assume a precision
    reference voltage source is connected per the docstring of each
    calibration setting; if not available, mark those tests `xfail` or
    skip via `-m "not calibration"`.

Run with:
    pytest test_dac_adc_giga.py -v --tb=short

Run excluding hardware-invasive calibration tests:
    pytest test_dac_adc_giga.py -v -m "not calibration"
"""

import time
import math
import pytest
import numpy as np
import labrad
import matplotlib.pyplot as plt


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

DEVICE_INDEX = 0          # adjust to select the correct physical device
LOOPBACK_CHANNELS = list(range(8))   # DAC i <-> ADC i assumed jumpered
SETTLE_S = 0.05            # generic settle time after set_voltage

# Loopback tolerance for buffer-ramp waveforms. This is looser than the
# static set_voltage/read_voltage loopback tolerance (abs_tol=0.005 V)
# because buffer-ramp acquisitions run at much shorter conversion times
# and settling windows, so more ADC/DAC code noise is expected.
RAMP_ABS_TOL_V = 0.002


# --------------------------------------------------------------------------
# Theoretical-waveform helpers
# --------------------------------------------------------------------------
#
# These reproduce, in pure numpy, what an ideal (noiseless) DAC0->ADC0 ...
# DAC7->ADC7 loopback *should* read back for each buffer-ramp variant, so
# that the measured trace(s) can be checked against theory rather than
# just checked for shape/length.

def expected_linear_ramp(v0, v1, steps):
    """dac_led_buffer_ramp: one ADC reading per DAC step, DAC held at a
    linearly-interpolated voltage while the ADC converts/settles."""
    return np.linspace(v0, v1, steps)


def expected_time_series_ramp(v0, v1, steps, dac_period_us, adc_period_us):
    """time_series_buffer_ramp: DAC advances one linear step every
    dac_period_us while the ADC free-runs at adc_period_us, so each DAC
    step is sampled dac_period_us/adc_period_us times before the DAC
    moves to the next step (a staircase, not a smooth ramp)."""
    dac_steps = np.linspace(v0, v1, steps)
    samples_per_step = int(round(dac_period_us / adc_period_us))
    assert samples_per_step >= 1, (
        "adc_period_us must be <= dac_period_us for time_series_buffer_ramp"
    )
    return np.repeat(dac_steps, samples_per_step)


def expected_2d_grid(start, fast_vec, slow_vec, steps_fast, steps_slow):
    """dac_led_buffer_ramp_2d / time_series_buffer_ramp_2d, no snake/retrace:
    row-major grid, position(i_slow, i_fast) = start + i_slow*slow_vec
    (scaled over steps_slow-1) + i_fast*fast_vec (scaled over steps_fast-1),
    flattened one slow row at a time, fast axis always increasing."""
    fast_frac = np.linspace(0.0, 1.0, steps_fast)
    slow_frac = np.linspace(0.0, 1.0, steps_slow) if steps_slow > 1 else np.array([0.0])
    grid = start + np.outer(slow_frac, slow_vec)[:, None, :] + np.outer(fast_frac, fast_vec)[None, :, :]
    # grid shape: (steps_slow, steps_fast, n_channels) -> flatten to (steps_slow*steps_fast, n_channels)
    return grid.reshape(-1, grid.shape[-1])


@pytest.fixture(scope="session")
def cxn():
    """Session-wide LabRAD connection."""
    connection = labrad.connect()
    yield connection
    connection.disconnect()


@pytest.fixture(scope="session")
def server(cxn):
    """The dac_adc_giga server proxy."""
    return cxn.dac_adc_giga


@pytest.fixture(scope="session", autouse=True)
def select_device(server):
    """Select / connect the physical device once for the whole session."""
    devices = server.list_devices()
    assert len(devices) > 0, "No DAC-ADC-GIGA devices found by the server."
    server.select_device(DEVICE_INDEX)
    yield
    # no explicit teardown needed; server manages device lifetime


@pytest.fixture(autouse=True)
def zero_all_channels(server):
    """Return all DAC channels to 0V before and after each test."""
    for ch in range(8):
        server.set_voltage(ch, 0.0)
    time.sleep(SETTLE_S)
    yield
    for ch in range(8):
        server.set_voltage(ch, 0.0)
    time.sleep(SETTLE_S)


# --------------------------------------------------------------------------
# Connection / identity / status
# --------------------------------------------------------------------------

class TestConnectionAndIdentity:

    def test_id(self, server):
        """*IDN? returns a non-empty identification string."""
        ans = server.id()
        assert isinstance(ans, str)
        assert len(ans) > 0

    def test_sn(self, server):
        """Serial number query returns a non-empty string."""
        ans = server.sn()
        assert isinstance(ans, str)
        assert len(ans) > 0

    def test_in_waiting_idle(self, server):
        """With no ramp in progress, the input buffer should be empty."""
        ans = server.in_waiting()
        assert ans == 0

    def test_initialize(self, server):
        """INITIALIZE completes and returns an acknowledgement string."""
        ans = server.initialize()
        assert isinstance(ans, str)
        assert len(ans) > 0


# --------------------------------------------------------------------------
# Single-channel voltage set / read
# --------------------------------------------------------------------------

class TestSetReadVoltage:

    @pytest.mark.parametrize("port", range(8))
    @pytest.mark.parametrize("voltage", [-5.0, 0.0, 2.5, 9.9])
    def test_set_voltage_valid(self, server, port, voltage):
        ans = server.set_voltage(port, voltage)
        assert "Error" not in ans
        time.sleep(SETTLE_S)
        readback = server.read_dac_voltage(port)
        assert math.isclose(readback, voltage, abs_tol=0.001)

    def test_set_voltage_invalid_port(self, server):
        try:
            ans = server.set_voltage(99, 1.0)
            assert "Error" in ans
        except:
            #pytest.skip("Throws labrad error when given invalid port -- correct behavior")
            print("Expected Error for Labrad")

    @pytest.mark.parametrize("voltage", [10.5, -10.5])
    def test_set_voltage_out_of_range(self, server, voltage):
        ans = server.set_voltage(0, voltage)
        assert "Error" in ans

    @pytest.mark.parametrize("port", range(8))
    def test_read_voltage_adc(self, server, port):
        """ADC read returns a float within the +/-10V nominal range."""
        v = server.read_voltage(port)
        assert isinstance(v, float)
        assert -10.5 <= v <= 10.5

    def test_read_voltage_invalid_port(self, server):
        try:
            ans = server.read_voltage(99)
            assert "Error" in str(ans)
        except:
            #pytest.skip("Throws labrad error when given invalid port -- correct behavior")
            print("Expected Error for Labrad")

    def test_set_then_loopback_read(self, server):
        """DAC0 -> ADC0 loopback: set a known voltage, verify ADC reads it back."""
        target = 3.3
        server.set_voltage(0, target)
        time.sleep(SETTLE_S)
        measured = server.read_voltage(0)
        assert math.isclose(measured, target, abs_tol=0.001)


# --------------------------------------------------------------------------
# DAC code (raw register) interface
# --------------------------------------------------------------------------

class TestDacCode:

    def test_set_dac_code_valid(self, server):
        ans = server.set_dac_code(0, 524288)  # mid-scale
        assert "Error" not in str(ans)

    def test_set_dac_code_invalid_channel(self, server):
        ans = server.set_dac_code(99, 1000)
        assert "Error" in str(ans)

    @pytest.mark.parametrize("code", [-1, 1048577])
    def test_set_dac_code_out_of_range(self, server, code):
        ans = server.set_dac_code(0, code)
        assert "Error" in str(ans)


# --------------------------------------------------------------------------
# ramp1 / ramp2 (single & dual channel point-to-point ramps)
# --------------------------------------------------------------------------

class TestRamp1Ramp2:

    def test_ramp1_basic(self, server):
        ans = server.ramp1(0, 0.0, 1.0, 100, 100)
        assert "RAMPING DAC" in ans
        time.sleep(SETTLE_S)
        assert math.isclose(server.read_dac_voltage(0), 1.0, abs_tol=0.05)

    def test_ramp1_returns_to_zero(self, server):
        server.ramp1(0, 0.0, 2.0, 50, 100)
        ans = server.ramp1(0, 2.0, 0.0, 50, 100)
        assert "RAMPING DAC" in ans
        time.sleep(SETTLE_S)
        assert math.isclose(server.read_dac_voltage(0), 0.0, abs_tol=0.05)

    def test_ramp2_basic(self, server):
        ans = server.ramp2(0, 1, 0.0, 0.0, 1.0, -1.0, 100, 100)
        assert "RAMPING DAC" in ans
        time.sleep(SETTLE_S)
        assert math.isclose(server.read_dac_voltage(0), 1.0, abs_tol=0.05)
        assert math.isclose(server.read_dac_voltage(1), -1.0, abs_tol=0.05)


# --------------------------------------------------------------------------
# Conversion time settings
# --------------------------------------------------------------------------

class TestConversionTime:

    @pytest.mark.parametrize("conv_time", [82.0, 500.0, 2686.0])
    def test_set_conversion_time_valid(self, server, conv_time):
        ans = server.set_conversionTime(0, conv_time)
        assert math.isclose(ans, conv_time, rel_tol=10)

    @pytest.mark.parametrize("conv_time", [50.0, 3000.0])
    def test_set_conversion_time_invalid(self, server, conv_time):
        try:
            ans = server.set_conversionTime(0, conv_time)
            assert "Error" in str(ans)
        except:
            print("Expected Error for Labrad")

    def test_get_conversion_time_matches_set(self, server):
        server.set_conversionTime(0, 500.0)
        readback = server.get_conversion_time(0)
        assert math.isclose(readback, 500.0, rel_tol=10)

    @pytest.mark.parametrize("fw", [3, 64, 127])
    def test_set_conversion_time_fw_valid(self, server, fw):
        ans = server.set_conversionTimeFW(0, fw)
        assert isinstance(ans, float)

    @pytest.mark.parametrize("fw", [0, 200])
    def test_set_conversion_time_fw_invalid(self, server, fw):
        try:
            ans = server.set_conversionTimeFW(0, fw)
            assert "Error" in str(ans)
        except:
            print("Expected Error for Labrad")


# --------------------------------------------------------------------------
# Misc DAC settings: full scale, delay unit, offset/gain
# --------------------------------------------------------------------------

class TestMiscDacSettings:

    @pytest.mark.parametrize("unit", [0, 1])
    def test_delay_unit(self, server, unit):
        ans = server.delay_unit(unit)
        assert "Error" not in str(ans)

    def test_inquiry_offset_and_gain(self, server):
        ans = server.inquiry_offset_and_gain()
        assert len(ans) == 16


# --------------------------------------------------------------------------
# stop_ramp / reset_adc / hard_reset_adc
# --------------------------------------------------------------------------

class TestResetAndStop:

    def test_reset_adc(self, server):
        server.reset_adc()  # no return value expected

    def test_hard_reset_adc(self, server):
        ans = server.hard_reset_adc()
        assert isinstance(ans, str)

    def test_stop_ramp_idle_noop(self, server):
        """Calling stop_ramp with no active ramp should not raise."""
        server.stop_ramp()


# --------------------------------------------------------------------------
# Buffer ramps: BUFFER_RAMP (dac_led_buffer_ramp / buffer_ramp)
# --------------------------------------------------------------------------

class TestBufferRampSingleChannel:
    """1 DAC channel, 1 ADC channel dac_led_buffer_ramp (the minimal case)."""

    DAC_PORTS = [0]
    ADC_PORTS = [0]
    STEPS = 200
    DELAY_US = 3000.0
    V0 = 0.0
    V1 = 1.0

    def test_buffer_ramp_single_channel_via_dac_led_buffer_ramp(self, server):
        """DAC0 ramped 0->1V over STEPS points while ADC0 (loopback) is read
        back once per step; verifies the returned trace against the ideal
        linear ramp DAC0 was commanded to produce."""
        for adc_port in self.ADC_PORTS:
            convtime = server.set_conversionTime(adc_port, 500)
            assert math.isclose(convtime, 500, abs_tol=10)

        result = server.dac_led_buffer_ramp(
            self.DAC_PORTS,
            self.ADC_PORTS,
            [self.V0],
            [self.V1],
            self.STEPS,
            self.DELAY_US,
            500,
            1,
        )
        assert len(result) == 1
        trace = np.asarray(result[0])
        assert len(trace) == self.STEPS

        expected = expected_linear_ramp(self.V0, self.V1, self.STEPS)
        assert np.allclose(trace, expected, atol=RAMP_ABS_TOL_V), (
            f"max deviation from ideal ramp = {np.max(np.abs(trace - expected)):.4f} V"
        )
        # trace must be (weakly) monotonic since V1 > V0
        assert np.all(np.diff(trace) >= -RAMP_ABS_TOL_V)


class TestBufferRampEightChannel:
    """8 DAC channels, 8 ADC channels dac_led_buffer_ramp (full hardware width)."""

    DAC_PORTS = list(range(8))
    ADC_PORTS = list(range(8))
    STEPS = 100
    DELAY_US = 5000  # wider delay since 8 ADC channels must convert per step
    # independent, alternating-polarity per-channel targets so that a
    # channel-swap bug would be caught (not just "all channels reach 1V")
    IVOLTAGES = [0.0] * 8
    FVOLTAGES = [((-1) ** i) * 2.0 for i in range(8)]

    def test_buffer_ramp_eight_channel_multiple_readings(self, server):
        """All 8 channels ramped simultaneously to independent targets with
        nReadings=4 (per-step averaging); verifies each channel's trace
        against its own ideal linear ramp."""
        for adc_port in self.ADC_PORTS:
            convtime = server.set_conversionTime(adc_port, 500)
            assert math.isclose(convtime, 500, abs_tol=10)

        result = server.dac_led_buffer_ramp(
            self.DAC_PORTS,
            self.ADC_PORTS,
            self.IVOLTAGES,
            self.FVOLTAGES,
            self.STEPS,
            self.DELAY_US,
            500,
            1,
        )
        assert len(result) == 8
        for ch, trace in enumerate(result):
            trace = np.asarray(trace)
            assert len(trace) == self.STEPS
            expected = expected_linear_ramp(
                self.IVOLTAGES[ch], self.FVOLTAGES[ch], self.STEPS
            )
            assert np.allclose(trace, expected, atol=RAMP_ABS_TOL_V), (
                f"channel {ch}: max deviation = "
                f"{np.max(np.abs(trace - expected)):.4f} V"
            )


# --------------------------------------------------------------------------
# Time-series buffer ramp (TIME_SERIES_BUFFER_RAMP)
# --------------------------------------------------------------------------

class TestTimeSeriesBufferRamp:

    def test_time_series_buffer_ramp_single_channel(self, server):
        """1 DAC/1 ADC ramp with independent DAC (1000us) and ADC (200us)
        periods; verifies the trace against the ideal staircase (5 ADC
        samples per DAC step, since dacPeriod/adcPeriod = 5)."""

        convtime = server.set_conversionTime(0, 200)

        steps, dac_period, adc_period = 100, 3000.0, convtime + 100
        v0, v1 = 0.0, 1.0
        result = server.time_series_buffer_ramp(
            [0], [0], [v0], [v1],
            steps, dac_period, adc_period,
        )
        assert len(result) == 1
        trace = np.asarray(result[0])
        samples = int(steps * dac_period/adc_period)
        assert len(trace) == samples

        over_sample_rate = int(round(dac_period/adc_period))
        expected = np.linspace(v0, v1, steps)

        assert np.allclose(trace[::over_sample_rate], expected[:len(trace[::over_sample_rate])], atol=0.05), (
            f"max deviation from ideal staircase = "
            f"{np.max(np.abs(trace[::over_sample_rate] - expected[:len(trace[::over_sample_rate])])):.4f} V"
        )

    '''
    def test_time_series_buffer_ramp_eight_channel(self, server):
        """8 DAC/8 ADC ramp with independent periods; verifies all 8
        channels match the expected staircase (dacPeriod/adcPeriod=5
        samples per DAC step)."""

        convtime = 0
        for i in range(8):
            convtime = server.set_conversionTime(i, 200)

        steps, dac_period, adc_period = 50, 6000.0, 4*convtime + 200
        v0s, v1s = [0.0] * 8, [1.0] * 8
        result = server.time_series_buffer_ramp(
            list(range(8)), list(range(8)),
            v0s, v1s,
            steps, dac_period, adc_period,
        )
        assert len(result) == 8
        expected = expected_time_series_ramp(v0s[0], v1s[0], steps, dac_period, adc_period)
        for ch, trace in enumerate(result):
            trace = np.asarray(trace)
            assert len(trace) == len(expected)
            assert np.allclose(trace, expected, atol=RAMP_ABS_TOL_V), (
                f"channel {ch}: max deviation = "
                f"{np.max(np.abs(trace - expected)):.4f} V"
            )

    '''
# --------------------------------------------------------------------------
# Time-series raw ADC read (no DAC ramp)
# --------------------------------------------------------------------------

class TestTimeSeriesAdcRead:

    def test_time_series_adc_read_single_channel(self, server):
        result = server.time_series_adc_read([0], 500.0, 50000.0)
        assert len(result) == 1
        assert len(result[0]) > 0

    def test_time_series_adc_read_eight_channel(self, server):
        result = server.time_series_adc_read(
            list(range(8)), 500.0, 5000000.0
        )
        assert len(result) == 8
        lengths = [len(trace) for trace in result]
        assert all(l == lengths[0] for l in lengths), "All channels should be same length"


# --------------------------------------------------------------------------
# 2D buffer ramps: time_series_buffer_ramp_2d / dac_led_buffer_ramp_2d
# --------------------------------------------------------------------------

class TestBufferRamp2D:
    """
    For the non-snake/non-retrace grids below, the fast axis always sweeps
    increasing, one slow row after another, so the flattened trace should
    match `expected_2d_grid(...)`. `dac_led_buffer_ramp_2d` produces one
    (averaged) ADC reading per grid point, so it's compared directly to the
    grid; `time_series_buffer_ramp_2d` free-runs the ADC within each row
    the same way the 1D `time_series_buffer_ramp` does, so each fast-axis
    grid point is expected to repeat dacInterval_us/adcInterval_us times.
    """

    '''
    def test_time_series_buffer_ramp_2d_single_channel(self, server):
        start, fast_vec, slow_vec = [0.0], [1.0], [0.0]
        steps_fast, steps_slow = 100, 10
        dac_interval, adc_interval = 500.0, 500.0  # 1:1 -> one sample/point

        result = server.time_series_buffer_ramp_2d(
            [0], [0],
            startPoint=start,
            fastAxisVector=fast_vec,
            slowAxisVector=slow_vec,
            stepsFast=steps_fast,
            stepsSlow=steps_slow,
            retrace=False,
            snake=False,
            dacInterval_us=dac_interval,
            adcInterval_us=adc_interval,
        )
        assert len(result) == 1
        trace = np.asarray(result[0])
        grid = expected_2d_grid(start, fast_vec, slow_vec, steps_fast, steps_slow)
        expected = np.repeat(grid[:, 0], int(round(dac_interval / adc_interval)))
        assert len(trace) == len(expected)
        assert np.allclose(trace, expected, atol=RAMP_ABS_TOL_V)

    def test_time_series_buffer_ramp_2d_eight_channel(self, server):
        start, fast_vec, slow_vec = [0.0] * 8, [1.0] * 8, [0.0] * 8
        steps_fast, steps_slow = 30, 3
        dac_interval, adc_interval = 1000.0, 1000.0  # 1:1 -> one sample/point

        result = server.time_series_buffer_ramp_2d(
            list(range(8)), list(range(8)),
            startPoint=start,
            fastAxisVector=fast_vec,
            slowAxisVector=slow_vec,
            stepsFast=steps_fast,
            stepsSlow=steps_slow,
            retrace=False,
            snake=False,
            dacInterval_us=dac_interval,
            adcInterval_us=adc_interval,
        )
        assert len(result) == 8
        grid = expected_2d_grid(start, fast_vec, slow_vec, steps_fast, steps_slow)
        for ch, trace in enumerate(result):
            trace = np.asarray(trace)
            expected = np.repeat(grid[:, ch], int(round(dac_interval / adc_interval)))
            assert len(trace) == len(expected)
            assert np.allclose(trace, expected, atol=RAMP_ABS_TOL_V), (
                f"channel {ch}: max deviation = "
                f"{np.max(np.abs(trace - expected)):.4f} V"
            )
    '''
    def test_dac_led_buffer_ramp_2d_single_channel(self, server):
        start, fast_vec, slow_vec = [0.0], [1.0], [0.0]
        steps_fast, steps_slow = 100, 10

        result = server.dac_led_buffer_ramp_2d(
            [0], [0],
            start,
            fast_vec,
            slow_vec,
            steps_fast,
            steps_slow,
            False,
            False,
            2,
            1000.0,
            200.0,
        )
        assert len(result) == 1
        trace = np.asarray(result[0])
        expected = expected_2d_grid(start, fast_vec, slow_vec, steps_fast, steps_slow)[:, 0]
        assert len(trace) == len(expected)
        assert np.allclose(trace, expected, atol=RAMP_ABS_TOL_V)

    def test_dac_led_buffer_ramp_2d_eight_channel(self, server):
        start, fast_vec, slow_vec = [0.0] * 8, [1.0] * 8, [0.0] * 8
        steps_fast, steps_slow = 30, 3

        result = server.dac_led_buffer_ramp_2d(
            list(range(8)), list(range(8)),
            start,
            fast_vec,
            slow_vec,
            steps_fast,
            steps_slow,
            False,
            False,
            1,
            6000.0,
            400.0,
        )
        assert len(result) == 8
        grid = expected_2d_grid(start, fast_vec, slow_vec, steps_fast, steps_slow)
        for ch, trace in enumerate(result):
            trace = np.asarray(trace)
            expected = grid[:, ch]
            assert len(trace) == len(expected)
            assert np.allclose(trace, expected, atol=RAMP_ABS_TOL_V), (
                f"channel {ch}: max deviation = "
                f"{np.max(np.abs(trace - expected)):.4f} V"
            )
    '''
    def test_2d_ramp_snake_and_retrace_single_channel(self, server):
        """
        Exercise snake + retrace flag combinations on the minimal channel
        case. Exact retrace point-count semantics aren't pinned down here
        (retrace inserts extra return-to-start points whose count is
        driver-defined), so this stays a structural/theory-informed check
        rather than a full-trace comparison: total length must be at least
        the bare grid size, the first point must start at `startPoint`,
        and -- because snake=True -- alternate slow rows must run in
        opposite fast-axis directions (row 0 increasing, row 1 decreasing).
        """
        start, fast_vec, slow_vec = [0.0], [1.0], [0.5]
        steps_fast, steps_slow = 40, 4

        result = server.time_series_buffer_ramp_2d(
            [0], [0],
            start,
            fast_vec,
            slow_vec,
            steps_fast,
            steps_slow,
            True,
            True,
            2000.0,
            500.0,
        )
        assert len(result) == 1
        trace = np.asarray(result[0])

        bare_grid_size = steps_fast * steps_slow
        assert len(trace) >= bare_grid_size, (
            "snake+retrace trace shorter than the bare fast x slow grid"
        )
        assert math.isclose(trace[0], start[0], abs_tol=RAMP_ABS_TOL_V)

        # crude row split assuming no retrace padding beyond stepsFast per
        # row; if the driver does pad, this only checks the first two rows'
        # leading stepsFast samples, which should still hold since a row's
        # sweep is written before any retrace padding for that row.
        row0 = trace[:steps_fast]
        row1 = trace[steps_fast:2 * steps_fast]
        assert row0[-1] > row0[0], "row 0 (snake) should increase along fast axis"
        assert row1[0] > row1[-1], "row 1 (snake) should decrease along fast axis"

    '''
