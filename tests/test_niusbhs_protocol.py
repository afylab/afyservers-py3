# SPDX-License-Identifier: GPL-2.0-or-later

import unittest

from niusbhs import constants as c
from niusbhs.protocol import (
    StatusBlock,
    build_command,
    build_init_writes,
    build_read,
    build_register_write,
    build_remote_enable_writes,
    build_write,
    mla,
    mta,
    parse_ibrd_readback,
    parse_reg_write_status_block,
    parse_status_block,
    timeout_code,
    timeout_msecs,
)


def status_bytes(block_id, ibsta=0x0120, error=0, count=0):
    comp = ((~count) + 1) & 0xFFFF
    return bytes((block_id, (ibsta >> 8) & 0xFF, ibsta & 0xFF, error, comp & 0xFF, comp >> 8, 0, 0))


class ProtocolTests(unittest.TestCase):
    def test_init_write_count_and_packet_header(self):
        writes = build_init_writes()
        self.assertEqual(len(writes), 26)
        packet = build_register_write(writes)
        self.assertEqual(packet[:6], bytes((0x09, 26, 0, 3, 0x10, 0)))
        self.assertEqual(packet[-4:], bytes((0x04, 0, 0, 0)))
        self.assertEqual(len(packet) % 4, 0)

    def test_command_packet_matches_ni_usb_command_chunk_layout(self):
        packet = build_command(bytes((c.UNL, mta(0), mla(19))), timeout_usec=1_000_000)
        self.assertEqual(packet, bytes.fromhex("0c fd 00 fb 3f 40 33 00 04 00 00 00"))

    def test_write_packet_matches_ni_usb_write_layout(self):
        packet = build_write(b"*IDN?", timeout_usec=1_000_000)
        self.assertEqual(packet, bytes.fromhex("0d fb ff fb 00 00 08 00 2a 49 44 4e 3f 00 00 00 04 00 00 00"))

    def test_read_packet_matches_ni_usb_read_prefix_and_embedded_register_writes(self):
        packet = build_read(1024, timeout_usec=1_000_000)
        self.assertEqual(packet[:8], bytes.fromhex("0a 00 00 fb 00 fc 00 00"))
        self.assertEqual(packet[8:17], bytes((0x09, 2, 0, 1, 10, 0x51, 1, 10, 0x55)))
        self.assertEqual(packet[-4:], bytes((0x04, 0, 0, 0)))

    def test_remote_enable_register_write_matches_ni_usb_remote_enable(self):
        packet = build_register_write(build_remote_enable_writes(True))
        self.assertEqual(packet, bytes.fromhex("09 01 00 01 0a 1f 00 00 04 00 00 00"))

    def test_parse_status_block_count_twos_complement(self):
        status = parse_status_block(status_bytes(0x38, count=5))
        self.assertEqual(status, StatusBlock(id=0x38, ibsta=0x0120, error_code=0, count=5))

    def test_float_timeouts_are_normalized_for_libusb(self):
        self.assertEqual(timeout_code(1_000_000.0), 0xFB)
        self.assertIsInstance(timeout_msecs(1_000_000.0), int)
        self.assertEqual(timeout_msecs(1_000_000.0), 4000)

    def test_parse_register_write_status(self):
        raw = status_bytes(0x09, count=0) + bytes((26, 0, 0, 0)) + bytes((0x04, 0, 0, 0))
        status, completed, consumed = parse_reg_write_status_block(raw)
        self.assertEqual(status.id, 0x09)
        self.assertEqual(completed, 26)
        self.assertEqual(consumed, 12)

    def test_parse_readback_normal_block(self):
        payload = b"hello"
        block = bytes((0x36,)) + payload + bytes(15 - len(payload))
        raw = (
            block
            + status_bytes(0x38, ibsta=c.END | c.CMPL, count=10)
            + bytes((0, len(payload), 0, 0))
            + status_bytes(0x09)
            + bytes((2, 0, 0, 0))
            + bytes((0x04, 0, 0, 0))
        )
        parsed = parse_ibrd_readback(raw, parsed_data_length=15)
        self.assertEqual(parsed.data, payload)
        self.assertEqual(parsed.actual_length, len(payload))
        self.assertEqual(parsed.status.id, 0x38)
        self.assertEqual(parsed.register_write_status.id, 0x09)
        self.assertEqual(parsed.consumed, len(raw))

    def test_parse_readback_extended_blocks(self):
        first = bytes(range(30))
        second_payload = b"abc"
        second = second_payload + bytes(30 - len(second_payload))
        raw = (
            bytes((0x37, 0)) + first
            + bytes((0x37, 0)) + second
            + status_bytes(0x38, ibsta=c.END | c.CMPL, count=0)
            + bytes((0, len(second_payload), 0, 0))
            + status_bytes(0x09)
            + bytes((2, 0, 0, 0))
            + bytes((0x04, 0, 0, 0))
        )
        parsed = parse_ibrd_readback(raw, parsed_data_length=64)
        self.assertEqual(parsed.data, first + second_payload)
        self.assertEqual(parsed.actual_length, 33)


if __name__ == "__main__":
    unittest.main()
