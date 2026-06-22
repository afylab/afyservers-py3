import argparse
from time import sleep

"""
1) set dac code to 0
2) read ag value
3) see direction of change
4) if positive, decrement dac code
5) if negative, increment dac code
6) repeat until voltage is within 1 LSB of 0
7) increment/decrement by 1 more code and see if that code is better
8) print dac code and ag value
9) set offset to the voltage corresponding to the dac code
10) set gain to 1
11) set voltage to 10 V
12) read ag value
13) calculate gain = ag value / 10
14) set gain
"""

MAX_CODE = 2**20 - 1
lsb_size = 20/(2**20 - 1) # V


def dac_code_to_voltage(dac_code):
    if dac_code <= 524287:
        return dac_code * 10 / 524287
    else:
        return (dac_code - 1048576) * 10 / 524288


def voltage_to_dac_code(voltage):
    if voltage >= 0:
        return int(voltage * 524287 / 10)
    else:
        return int(voltage * 524288 / 10) + 1048576


cxn = None
da = None
ag = None


def connect_instruments():
    global cxn, da, ag
    if cxn is not None:
        return

    import labrad

    cxn = labrad.connect()

    da = cxn.dac_adc_giga()
    da.select_device()
    da.initialize()

    ag = cxn.agilent_34401a_dmm()
    ag.select_device()


def direction_from_meter_value(ag_value):
    if ag_value > 0:
        return -1
    if ag_value < 0:
        return 1
    return 0


def parse_channel_selection(channel_args, default_all=True):
    if not channel_args:
        return list(range(8)) if default_all else []

    channels = []
    for channel_arg in channel_args:
        for part in channel_arg.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start, end = [int(value) for value in part.split("-", 1)]
                step = 1 if start <= end else -1
                channels.extend(range(start, end + step, step))
            else:
                channels.append(int(part))

    invalid_channels = [channel for channel in channels if channel not in range(8)]
    if invalid_channels:
        raise ValueError(f"Invalid DAC channel(s): {invalid_channels}")

    return list(dict.fromkeys(channels))


def should_calibrate_channel(channel):
    response = input(
        f"Press enter to calibrate channel {channel}, "
        "s to skip, or q to quit: "
    ).strip().lower()
    if response in ("s", "skip"):
        print(f"SKIPPING CHANNEL {channel}.")
        return False
    if response in ("q", "quit", "exit"):
        raise KeyboardInterrupt
    return True

def calibrate_dac_channel(channel):
    connect_instruments()

    
    ### calibrate offset

    # quickly find heuristic
    ag.configure_voltage(10, 0.00001)

    dac_code = 0
    da.set_dac_code(channel,dac_code)
    sleep(0.1)
    old_ag_value = ag.read_voltage()

    heuristic_dac_code = voltage_to_dac_code(-1.0 * old_ag_value)

    ag.configure_voltage(0.01, 0.0000001)
    da.set_dac_code(channel,heuristic_dac_code)
    sleep(0.1)
    ag_value = ag.read_voltage()
    print(f"HEURISTIC DAC CODE: {heuristic_dac_code}, AG VALUE: {ag_value}")

    # sweep until +/- 1 LSB measured.
    # ag.configure_voltage(0.01, 0.0000001)

    dac_code = heuristic_dac_code
    da.set_dac_code(channel,dac_code)
    sleep(0.1)
    ag_value = ag.read_voltage()

    while abs(ag_value) > lsb_size:
        direction = direction_from_meter_value(ag_value)
        if direction == 0:
            break
        dac_code = (dac_code + direction) % (MAX_CODE + 1)
        da.set_dac_code(channel, dac_code)
        sleep(0.1)
        ag_value = ag.read_voltage()

    direction = direction_from_meter_value(ag_value)
    if direction != 0:
        dac_code = (dac_code + direction) % (MAX_CODE + 1)

        da.set_dac_code(channel,dac_code)
        sleep(0.1)
        ag_value_2 = ag.read_voltage()

        if abs(ag_value_2) < abs(ag_value):
            ag_value = ag_value_2
        else:
            dac_code = (dac_code - direction) % (MAX_CODE + 1)

    da.set_dac_code(channel,dac_code)

    print(f"DAC code: {dac_code}, AG value: {ag_value}")

    offset = -dac_code_to_voltage(dac_code)

    da.set_offset_and_gain(channel, offset, 1)

    da.set_voltage(channel, 0)

    print(f"OFFSET CALIBRATED. OLD 0 V = {old_ag_value} V; NEW 0 V = {ag.read_voltage()} V")

    ### calibrate gain

    ag.configure_voltage(10, 0.00001)

    da.set_voltage(channel, 10)
    sleep(0.1)
    ag_value = ag.read_voltage()
    old_10v = ag_value

    gain = ag_value/10

    da.set_offset_and_gain(channel, offset, gain)

    da.set_voltage(channel, 10)

    print(f"GAIN CALIBRATED. OLD 10 V = {old_10v} V; NEW 10 V = {ag.read_voltage()} V")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Calibrate selected DAC channels with an Agilent DMM."
    )
    parser.add_argument(
        "channels",
        nargs="*",
        help="DAC channels to calibrate. Supports values like '2', '0 2', or '0-3'. Defaults to all channels.",
    )
    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        help="DAC channels to skip from the selected channel list.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Run selected channel calibrations without prompting.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    selected_channels = parse_channel_selection(args.channels)
    skipped_channels = set(parse_channel_selection(args.skip, default_all=False))

    for channel in selected_channels:
        if channel in skipped_channels:
            print(f"SKIPPING CHANNEL {channel}.")
            continue
        if not args.yes and not should_calibrate_channel(channel):
            continue
        print(f"CALIBRATING CHANNEL {channel}...")
        calibrate_dac_channel(channel)
        user_input = input(f"CONNECT DAC CHANNEL {channel} TO ADC CHANNEL {channel}, then press Enter to continue calibration, or type 'skip' to skip this step: ")
        if user_input.strip().lower() == 'skip':
            print(f"SKIPPING ADC CALIBRATION FOR CHANNEL {channel}.")
            continue
        
        da.set_conversionTime(channel,2800)
        da.set_voltage(channel,0)
        sleep(0.1)
        da.calibrate_adc_channel_zero_scale(channel)
        sleep(0.1)
        da.set_voltage(channel,10)
        sleep(0.1)
        da.calibrate_adc_channel_zero_scale(channel)
        sleep(0.1)
        adc_reading_10v = da.read_voltage(channel)
        sleep(0.1)
        da.set_voltage(channel,0)
        sleep(0.1)
        adc_reading_0v = da.read_voltage(channel)
        print(f"ADC CHANNEL {channel} CALIBRATED. 0V reads {adc_reading_0v} and 10V reads {adc_reading_10v}.")