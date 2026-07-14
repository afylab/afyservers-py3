#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import niusbhs as visa


def main() -> None:
    parser = argparse.ArgumentParser(description="Query *IDN? through an NI GPIB-USB-HS adapter.")
    parser.add_argument("pad", type=int, help="GPIB primary address")
    parser.add_argument("--timeout-ms", type=int, default=1000)
    parser.add_argument("--debug", action="store_true", help="dump raw USB packets and decoded status blocks")
    args = parser.parse_args()

    if args.debug:
        os.environ["NIUSBHS_DEBUG"] = "1"
    rm = visa.ResourceManager()
    instr = rm.open_resource(f"GPIB0::{args.pad}::INSTR")
    instr.timeout = args.timeout_ms
    instr.bus.debug = args.debug
    instr.write_termination = ""
    print(instr.query("*IDN?").strip())


if __name__ == "__main__":
    main()
