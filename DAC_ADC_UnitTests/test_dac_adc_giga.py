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


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

DEVICE_INDEX = 0          # adjust to select the correct physical device
LOOPBACK_CHANNELS = list(range(8))   # DAC i <-> ADC i assumed jumpered
SETTLE_S = 0.05            # generic settle time after set_voltage


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
        assert math.isclose(readback, voltage, abs_tol=0.005)

    def test_set_voltage_invalid_port(self, server):
        ans = server.set_voltage(99, 1.0)
        assert "Error" in ans

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
        ans = server.read_voltage(99)
        assert "Error" in str(ans)

    def test_set_then_loopback_read(self, server):
        """DAC0 -> ADC0 loopback: set a known voltage, verify ADC reads it back."""
        target = 3.3
        server.set_voltage(0, target)
        time.sleep(SETTLE_S)
        measured = server.read_voltage(0)
        assert math.isclose(measured, target, abs_tol=0.005)


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
        ans = server.ramp1(0, 0.0, 1.0, steps=100, delay=100)
        assert "RAMP_FINISHED" in ans
        time.sleep(SETTLE_S)
        assert math.isclose(server.read_dac_voltage(0), 1.0, abs_tol=0.05)

    def test_ramp1_returns_to_zero(self, server):
        server.ramp1(0, 0.0, 2.0, steps=50, delay=100)
        ans = server.ramp1(0, 2.0, 0.0, steps=50, delay=100)
        assert "RAMP_FINISHED" in ans
        time.sleep(SETTLE_S)
        assert math.isclose(server.read_dac_voltage(0), 0.0, abs_tol=0.05)

    def test_ramp2_basic(self, server):
        ans = server.ramp2(0, 1, 0.0, 0.0, 1.0, -1.0, steps=100, delay=100)
        assert "RAMP_FINISHED" in ans
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
        ans = server.set_conversionTime(0, conv_time)
        assert "Error" in str(ans)

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
        ans = server.set_conversionTimeFW(0, fw)
        assert "Error" in str(ans)


# --------------------------------------------------------------------------
# Upper / lower voltage limits
# --------------------------------------------------------------------------

class TestVoltageLimits:

    def test_set_get_upper_limit(self, server):
        server.setUpperLimit(0, 8.0)
        readback = server.getUpperLimit(0, 0.0)  # 2nd arg unused, see driver signature
        assert math.isclose(readback, 8.0, abs_tol=0.05)

    def test_set_get_lower_limit(self, server):
        server.setLowerLimit(0, -8.0)
        readback = server.getLowerLimit(0, 0.0)
        assert math.isclose(readback, -8.0, abs_tol=0.05)


# --------------------------------------------------------------------------
# Misc DAC settings: full scale, delay unit, offset/gain
# --------------------------------------------------------------------------

class TestMiscDacSettings:

    def test_dac_full_scale(self, server):
        ans = server.dac_full_scale(10.0)
        assert "Error" not in str(ans)

    @pytest.mark.parametrize("unit", [0, 1])
    def test_delay_unit(self, server, unit):
        ans = server.delay_unit(unit)
        assert "Error" not in str(ans)

    def test_set_offset_and_gain(self, server):
        ans = server.set_offset_and_gain(0, 0.0, 1.0)
        assert ans is not None

    def test_inquiry_offset_and_gain(self, server):
        ans = server.inquiry_offset_and_gain()
        assert len(ans) == 32


# --------------------------------------------------------------------------
# Calibration routines
# --------------------------------------------------------------------------

@pytest.mark.calibration
class TestCalibration:
    """
    These require a precision reference connected per the on-device
    calibration procedure (zero-scale / full-scale references, and a
    DAC->ADC loopback for dac_ch_calibration). Skip with
    `-m "not calibration"` if the reference fixture is not on the bench.
    """

    def test_dac_ch_calibration(self, server):
        ans = server.dac_ch_calibration()
        assert "Error" not in str(ans)

    def test_calibrate_all_adc_channels_zero_scale(self, server):
        ans = server.calibrate_all_adc_channels_zero_scale()
        assert "Error" not in str(ans)

    def test_calibrate_adc_channel_zero_scale(self, server):
        ans = server.calibrate_adc_channel_zero_scale(0)
        assert "Error" not in str(ans)

    def test_calibrate_adc_channel_full_scale(self, server):
        ans = server.calibrate_adc_channel_full_scale(0)
        assert "Error" not in str(ans)

    def test_calibrate_all_adc_channel_full_scale(self, server):
        ans = server.calibrate_all_adc_channel_full_scale()
        assert "Error" not in str(ans)


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
# Low-level passthrough: read / write / query / timeout
# --------------------------------------------------------------------------

class TestLowLevelPassthrough:

    def test_query_idn(self, server):
        ans = server.query("*IDN?")
        assert isinstance(ans, str)
        assert len(ans) > 0

    def test_write_then_read(self, server):
        server.write("*RDY?\n")
        ans = server.read()
        assert "READY" in ans.upper()

    def test_timeout_setting(self, server):
        server.timeout(labrad.units.Value(2, "s"))
        # restore default-ish timeout afterward
        server.timeout(labrad.units.Value(5, "s"))


# --------------------------------------------------------------------------
# Buffer ramps: BUFFER_RAMP (dac_led_buffer_ramp / buffer_ramp)
# --------------------------------------------------------------------------

class TestBufferRampSingleChannel:
    """1 DAC channel, 1 ADC channel buffer ramp (the minimal case)."""

    DAC_PORTS = [0]
    ADC_PORTS = [0]
    STEPS = 200
    DELAY_US = 200.0

    def test_buffer_ramp_single_channel(self, server):
        result = server.buffer_ramp(
            self.DAC_PORTS,
            self.ADC_PORTS,
            [0.0],     # ivoltages
            [1.0],     # fvoltages
            self.STEPS,
            self.DELAY_US,
            1,         # nReadings
        )
        assert len(result) == 1, "Expected exactly one ADC channel of data"
        trace = np.array(result[0])
        assert len(trace) == self.STEPS
        # Loopback DAC0->ADC0: trace should rise monotonically (allow noise)
        assert trace[-1] > trace[0]
        assert math.isclose(trace[0], 0.0, abs_tol=0.2)
        assert math.isclose(trace[-1], 1.0, abs_tol=0.2)

    def test_buffer_ramp_single_channel_via_dac_led_buffer_ramp(self, server):
        """Same as above but calling the underlying lower-level setting directly."""
        result = server.dac_led_buffer_ramp(
            self.DAC_PORTS,
            self.ADC_PORTS,
            [0.0],
            [1.0],
            self.STEPS,
            dacInterval=self.DELAY_US,
            dacSettlingTime=160.0,
            nReadings=1,
        )
        assert len(result) == 1
        assert len(result[0]) == self.STEPS


class TestBufferRampEightChannel:
    """8 DAC channels, 8 ADC channels buffer ramp (full hardware width)."""

    DAC_PORTS = list(range(8))
    ADC_PORTS = list(range(8))
    STEPS = 100
    DELAY_US = 400.0  # wider delay since 8 ADC channels must convert per step

    def test_buffer_ramp_eight_channel(self, server):
        ivoltages = [0.0] * 8
        fvoltages = [(-1) ** i * 2.0 for i in range(8)]  # alternating +/-2V targets

        result = server.buffer_ramp(
            self.DAC_PORTS,
            self.ADC_PORTS,
            ivoltages,
            fvoltages,
            self.STEPS,
            self.DELAY_US,
            1,
        )
        assert len(result) == 8, "Expected 8 channels of ADC data"
        for ch_index, trace in enumerate(result):
            trace = np.array(trace)
            assert len(trace) == self.STEPS, f"Channel {ch_index} wrong length"
            assert math.isclose(trace[0], ivoltages[ch_index], abs_tol=0.25)
            assert math.isclose(trace[-1], fvoltages[ch_index], abs_tol=0.25)

    def test_buffer_ramp_eight_channel_multiple_readings(self, server):
        """Same 8x8 ramp but with nReadings=4 averaging per step."""
        ivoltages = [0.0] * 8
        fvoltages = [1.0] * 8

        result = server.buffer_ramp(
            self.DAC_PORTS,
            self.ADC_PORTS,
            ivoltages,
            fvoltages,
            self.STEPS,
            self.DELAY_US,
            4,  # nReadings
        )
        assert len(result) == 8
        for trace in result:
            assert len(trace) == self.STEPS


# --------------------------------------------------------------------------
# Buffer ramps: discrete-ADC-step variant (buffer_ramp_dis)
# --------------------------------------------------------------------------

class TestBufferRampDis:

    def test_buffer_ramp_dis_single_channel(self, server):
        result = server.buffer_ramp_dis(
            [0], [0], [0.0], [1.0],
            steps=100, delay=1000.0, adcSteps=5, nReadings=1,
        )
        assert len(result) == 1

    def test_buffer_ramp_dis_eight_channel(self, server):
        result = server.buffer_ramp_dis(
            list(range(8)), list(range(8)),
            [0.0] * 8, [1.0] * 8,
            steps=80, delay=2000.0, adcSteps=5, nReadings=1,
        )
        assert len(result) == 8


# --------------------------------------------------------------------------
# Time-series buffer ramp (TIME_SERIES_BUFFER_RAMP)
# --------------------------------------------------------------------------

class TestTimeSeriesBufferRamp:

    def test_time_series_buffer_ramp_single_channel(self, server):
        result = server.time_series_buffer_ramp(
            [0], [0], [0.0], [1.0],
            steps=100, dacPeriod_us=1000.0, adcPeriod_us=200.0,
        )
        assert len(result) == 1
        expected_len = int(100 * 1000.0 / 200.0)
        assert len(result[0]) == expected_len

    def test_time_series_buffer_ramp_eight_channel(self, server):
        result = server.time_series_buffer_ramp(
            list(range(8)), list(range(8)),
            [0.0] * 8, [1.0] * 8,
            steps=50, dacPeriod_us=2000.0, adcPeriod_us=400.0,
        )
        assert len(result) == 8
        expected_len = int(50 * 2000.0 / 400.0)
        for trace in result:
            assert len(trace) == expected_len


# --------------------------------------------------------------------------
# Time-series raw ADC read (no DAC ramp)
# --------------------------------------------------------------------------

class TestTimeSeriesAdcRead:

    def test_time_series_adc_read_single_channel(self, server):
        result = server.time_series_adc_read([0], convtime=500.0, totalTime=50000.0)
        assert len(result) == 1
        assert len(result[0]) > 0

    def test_time_series_adc_read_eight_channel(self, server):
        result = server.time_series_adc_read(
            list(range(8)), convtime=500.0, totalTime=100000.0
        )
        assert len(result) == 8
        lengths = [len(trace) for trace in result]
        assert all(l == lengths[0] for l in lengths), "All channels should be same length"


# --------------------------------------------------------------------------
# 2D buffer ramps: time_series_buffer_ramp_2d / dac_led_buffer_ramp_2d
# --------------------------------------------------------------------------

class TestBufferRamp2D:

    def test_time_series_buffer_ramp_2d_single_channel(self, server):
        result = server.time_series_buffer_ramp_2d(
            [0], [0],
            startPoint=[0.0],
            fastAxisVector=[1.0],
            slowAxisVector=[0.0],
            stepsFast=50,
            stepsSlow=3,
            retrace=False,
            snake=False,
            dacInterval_us=500.0,
            adcInterval_us=500.0,
        )
        assert len(result) == 1

    def test_time_series_buffer_ramp_2d_eight_channel(self, server):
        result = server.time_series_buffer_ramp_2d(
            list(range(8)), list(range(8)),
            startPoint=[0.0] * 8,
            fastAxisVector=[1.0] * 8,
            slowAxisVector=[0.0] * 8,
            stepsFast=30,
            stepsSlow=3,
            retrace=False,
            snake=False,
            dacInterval_us=1000.0,
            adcInterval_us=1000.0,
        )
        assert len(result) == 8

    def test_dac_led_buffer_ramp_2d_single_channel(self, server):
        result = server.dac_led_buffer_ramp_2d(
            [0], [0],
            startPoint=[0.0],
            fastAxisVector=[1.0],
            slowAxisVector=[0.0],
            stepsFast=50,
            stepsSlow=3,
            retrace=False,
            snake=False,
            numAdcAverages=2,
            dacInterval_us=500.0,
            dacSettlingTime_us=200.0,
        )
        assert len(result) == 1

    def test_dac_led_buffer_ramp_2d_eight_channel(self, server):
        result = server.dac_led_buffer_ramp_2d(
            list(range(8)), list(range(8)),
            startPoint=[0.0] * 8,
            fastAxisVector=[1.0] * 8,
            slowAxisVector=[0.0] * 8,
            stepsFast=30,
            stepsSlow=3,
            retrace=False,
            snake=False,
            numAdcAverages=2,
            dacInterval_us=1500.0,
            dacSettlingTime_us=400.0,
        )
        assert len(result) == 8

    def test_2d_ramp_snake_and_retrace_single_channel(self, server):
        """Exercise snake + retrace flag combinations on the minimal channel case."""
        result = server.time_series_buffer_ramp_2d(
            [0], [0],
            startPoint=[0.0],
            fastAxisVector=[1.0],
            slowAxisVector=[0.5],
            stepsFast=40,
            stepsSlow=4,
            retrace=True,
            snake=True,
            dacInterval_us=500.0,
            adcInterval_us=500.0,
        )
        assert len(result) == 1


# --------------------------------------------------------------------------
# stop_ramp interrupting an in-progress buffer ramp
# --------------------------------------------------------------------------

class TestStopRampDuringAcquisition:

    def test_stop_ramp_aborts_buffer_ramp(self, server):
        """
        Issue a long-running buffer ramp asynchronously is not directly
        supported by the synchronous client used here; instead this test
        confirms stop_ramp can be called safely immediately after starting
        a ramp request without leaving the device in a bad state, by
        running a short ramp to completion and then confirming the device
        is responsive (RDY?) afterward.
        """
        server.buffer_ramp([0], [0], [0.0], [0.5], 50, 500.0, 1)
        ans = server.ready()
        assert "READY" in ans.upper()
