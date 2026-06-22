# SPDX-License-Identifier: GPL-2.0-or-later
#
# Pure packet framing for the NI GPIB-USB-HS userspace driver.
# The byte layouts are derived from linux-gpib ni_usb_gpib.c.

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from . import constants as c


@dataclass(frozen=True)
class Register:
    device: int
    address: int
    value: int

    def bytes(self) -> bytes:
        return bytes((self.device & 0xFF, self.address & 0xFF, self.value & 0xFF))


@dataclass(frozen=True)
class StatusBlock:
    id: int
    ibsta: int
    error_code: int
    count: int

    @property
    def error_name(self) -> str:
        return c.NIUSB_ERROR_NAMES.get(self.error_code, f"UNKNOWN_{self.error_code}")


@dataclass(frozen=True)
class Readback:
    data: bytes
    status: StatusBlock
    register_write_status: StatusBlock
    consumed: int
    actual_length: int


def nec7210_to_tnt4882_offset(offset: int) -> int:
    return 2 * offset


def restrict_gpib_address(addr: int) -> int:
    addr &= 0x1F
    return 0 if addr == 0x1F else addr


def mla(addr: int) -> int:
    return c.LAD | restrict_gpib_address(addr)


def mta(addr: int) -> int:
    return c.TAD | restrict_gpib_address(addr)


def msa(addr: int) -> int:
    return c.SAD | (addr & 0x1F)


def timeout_code(usec: int) -> int:
    usec = int(usec)
    if usec == 0:
        return 0xF0
    if usec <= 10:
        return 0xF1
    if usec <= 30:
        return 0xF2
    if usec <= 100:
        return 0xF3
    if usec <= 300:
        return 0xF4
    if usec <= 1000:
        return 0xF5
    if usec <= 3000:
        return 0xF6
    if usec <= 10000:
        return 0xF7
    if usec <= 30000:
        return 0xF8
    if usec <= 100000:
        return 0xF9
    if usec <= 300000:
        return 0xFA
    if usec <= 1000000:
        return 0xFB
    if usec <= 3000000:
        return 0xFC
    if usec <= 10000000:
        return 0xFD
    if usec <= 30000000:
        return 0xFE
    if usec <= 100000000:
        return 0xFF
    if usec <= 300000000:
        return 0x01
    if usec <= 1000000000:
        return 0x02
    return 0xF0


def timeout_msecs(usec: int) -> int | None:
    usec = int(usec)
    if usec == 0:
        return None
    return 2000 + usec // 500


def _pad4(buf: bytearray) -> None:
    while len(buf) % 4:
        buf.append(0)


def bulk_termination() -> bytes:
    return bytes((c.NIUSB_TERM_ID, 0, 0, 0))


def build_register_write(registers: Iterable[Register]) -> bytes:
    regs = tuple(registers)
    if len(regs) > 0xFF:
        raise ValueError("NI register-write packet count is one byte")
    out = bytearray((c.NIUSB_REG_WRITE_ID, len(regs), 0))
    for reg in regs:
        out.extend(reg.bytes())
    _pad4(out)
    out.extend(bulk_termination())
    return bytes(out)


def setup_t1_delay(nano_sec: int = 2000) -> tuple[Register, Register, Register]:
    auxmr = nec7210_to_tnt4882_offset(c.AUXMR)
    first = c.AUXRI | c.SISB
    second = c.AUXRB
    third = 0
    if nano_sec <= 1100:
        first = c.AUXRI | c.USTD | c.SISB
    if nano_sec <= 500:
        second = c.AUXRB | c.HR_TRI
    if nano_sec <= 350:
        third = c.MSTD
    return (
        Register(c.NIUSB_SUBDEV_TNT4882, auxmr, first),
        Register(c.NIUSB_SUBDEV_TNT4882, auxmr, second),
        Register(c.NIUSB_SUBDEV_TNT4882, c.KEYREG, third),
    )


def build_sad_writes(address: int = 0, enable: bool = False) -> tuple[Register, ...]:
    adr_bits = c.HR_ARS
    admr_bits = c.HR_TRM0 | c.HR_TRM1
    if enable:
        adr_bits |= address
        admr_bits |= c.HR_ADM1
    else:
        adr_bits |= c.HR_DT | c.HR_DL
        admr_bits |= c.HR_ADM0
    return (
        Register(c.NIUSB_SUBDEV_TNT4882, nec7210_to_tnt4882_offset(c.ADR), adr_bits),
        Register(c.NIUSB_SUBDEV_TNT4882, nec7210_to_tnt4882_offset(c.ADMR), admr_bits),
        Register(c.NIUSB_SUBDEV_UNKNOWN2, 0x01, msa(address) if enable else 0),
    )


def build_init_writes(
    *,
    pad: int = 0,
    sad: int = -1,
    master: bool = True,
    eos_mode: int = 0,
    t1_nano_sec: int = 2000,
) -> tuple[Register, ...]:
    auxmr = nec7210_to_tnt4882_offset(c.AUXMR)
    mask = c.AUXRA | c.HR_HLDA
    if eos_mode & c.BIN:
        mask |= c.HR_BIN

    writes: list[Register] = [
        Register(c.NIUSB_SUBDEV_UNKNOWN3, 0x10, 0),
        Register(c.NIUSB_SUBDEV_TNT4882, c.CMDR, c.SOFT_RESET),
        Register(c.NIUSB_SUBDEV_TNT4882, auxmr, mask),
        Register(c.NIUSB_SUBDEV_TNT4882, c.AUXCR, mask),
        Register(c.NIUSB_SUBDEV_TNT4882, c.HSSEL, c.TNT_ONE_CHIP_BIT),
        Register(c.NIUSB_SUBDEV_TNT4882, auxmr, c.AUX_CR),
        Register(c.NIUSB_SUBDEV_TNT4882, c.IMR0, c.TNT_IMR0_ALWAYS_BITS),
        Register(c.NIUSB_SUBDEV_TNT4882, nec7210_to_tnt4882_offset(c.IMR1), 0),
        Register(c.NIUSB_SUBDEV_TNT4882, nec7210_to_tnt4882_offset(c.IMR2), 0),
        Register(c.NIUSB_SUBDEV_TNT4882, c.IMR3, 0),
        Register(c.NIUSB_SUBDEV_TNT4882, auxmr, c.AUX_HLDI),
    ]
    writes.extend(setup_t1_delay(t1_nano_sec))
    writes.extend(
        (
            Register(c.NIUSB_SUBDEV_TNT4882, auxmr, c.AUXRG | c.NTNL_BIT),
            Register(c.NIUSB_SUBDEV_TNT4882, c.CMDR, c.SETSC if master else c.CLRSC),
            Register(c.NIUSB_SUBDEV_TNT4882, auxmr, c.AUX_CIFC),
            Register(c.NIUSB_SUBDEV_TNT4882, nec7210_to_tnt4882_offset(c.ADR), pad),
            Register(c.NIUSB_SUBDEV_UNKNOWN2, 0x00, pad),
        )
    )
    writes.extend(build_sad_writes(sad if sad >= 0 else 0, sad >= 0))
    writes.extend(
        (
            Register(c.NIUSB_SUBDEV_UNKNOWN2, 0x02, 0xFD),
            Register(c.NIUSB_SUBDEV_TNT4882, 0x0F, 0x11),
            Register(c.NIUSB_SUBDEV_TNT4882, auxmr, c.AUX_PON),
            Register(c.NIUSB_SUBDEV_TNT4882, auxmr, c.AUX_CPPF),
        )
    )
    return tuple(writes)


def build_remote_enable_writes(enable: bool = True) -> tuple[Register, ...]:
    return (
        Register(
            c.NIUSB_SUBDEV_TNT4882,
            nec7210_to_tnt4882_offset(c.AUXMR),
            c.AUX_SREN if enable else c.AUX_CREN,
        ),
    )


def _complement_minus_one(length: int) -> int:
    if length < 1 or length > 0x10000:
        raise ValueError("length must be in 1..65536")
    return (~(length - 1)) & 0xFFFF


def build_command(command_bytes: bytes | bytearray | Sequence[int], *, timeout_usec: int) -> bytes:
    data = bytes(command_bytes)
    if not data:
        raise ValueError("command must contain at least one byte")
    if len(data) > 0x10:
        raise ValueError("ni_usb_command_chunk sends at most 16 command bytes")
    out = bytearray((0x0C, _complement_minus_one(len(data)) & 0xFF, 0, timeout_code(timeout_usec)))
    out.extend(data)
    _pad4(out)
    out.extend(bulk_termination())
    return bytes(out)


def build_write(data: bytes | bytearray | str, *, send_eoi: bool = True, timeout_usec: int) -> bytes:
    payload = data.encode() if isinstance(data, str) else bytes(data)
    comp = _complement_minus_one(len(payload))
    out = bytearray((0x0D, comp & 0xFF, (comp >> 8) & 0xFF, timeout_code(timeout_usec), 0, 0))
    out.append(0x08 if send_eoi else 0)
    out.append(0)
    out.extend(payload)
    _pad4(out)
    out.extend(bulk_termination())
    return bytes(out)


def build_read(
    length: int,
    *,
    eos_mode: int = 0,
    eos_char: int = 0,
    timeout_usec: int,
) -> bytes:
    comp = _complement_minus_one(length)
    auxmr = nec7210_to_tnt4882_offset(c.AUXMR)
    out = bytearray(
        (
            0x0A,
            (eos_mode >> 8) & 0xFF,
            eos_char & 0xFF,
            timeout_code(timeout_usec),
            comp & 0xFF,
            (comp >> 8) & 0xFF,
            0,
            0,
        )
    )
    out.extend((c.NIUSB_REG_WRITE_ID, 2, 0))
    out.extend(Register(c.NIUSB_SUBDEV_TNT4882, auxmr, c.AUX_HLDI).bytes())
    out.extend(Register(c.NIUSB_SUBDEV_TNT4882, auxmr, c.AUX_CLEAR_END).bytes())
    _pad4(out)
    out.extend(bulk_termination())
    return bytes(out)


def build_take_control(*, synchronous: bool) -> bytes:
    return bytes((c.NIUSB_IBCAC_ID, 1 if synchronous else 0, 0, 0)) + bulk_termination()


def build_go_to_standby() -> bytes:
    return bytes((c.NIUSB_IBGTS_ID, 0, 0, 0)) + bulk_termination()


def build_interface_clear() -> bytes:
    return bytes((c.NIUSB_IBSIC_ID, 0, 0, 0)) + bulk_termination()


def parse_status_block(buffer: bytes | bytearray | memoryview, offset: int = 0) -> StatusBlock:
    raw = bytes(buffer)
    if len(raw) - offset < 8:
        raise ValueError("status block requires 8 bytes")
    count = raw[offset + 4] | (raw[offset + 5] << 8)
    count = ((~count) + 1) & 0xFFFF
    return StatusBlock(
        id=raw[offset],
        ibsta=(raw[offset + 1] << 8) | raw[offset + 2],
        error_code=raw[offset + 3],
        count=count,
    )


def parse_reg_write_status_block(raw_data: bytes | bytearray | memoryview) -> tuple[StatusBlock, int, int]:
    raw = bytes(raw_data)
    status = parse_status_block(raw, 0)
    writes_completed = raw[8]
    consumed = 9
    while consumed % 4:
        consumed += 1
    return status, writes_completed, consumed


def parse_termination_block(raw_data: bytes | bytearray | memoryview, offset: int = 0) -> int:
    raw = bytes(raw_data)
    if raw[offset : offset + 4] != bulk_termination():
        got = raw[offset : offset + 4].hex(" ")
        raise ValueError(f"unexpected termination block at {offset}: {got}")
    return 4


def parse_ibrd_readback(
    raw_data: bytes | bytearray | memoryview,
    *,
    parsed_data_length: int,
) -> Readback:
    raw = bytes(raw_data)
    i = 0
    parsed = bytearray()
    num_data_blocks = 0
    data_block_length = 0

    while i < len(raw) and raw[i] in (c.NIUSB_IBRD_DATA_ID, c.NIUSB_IBRD_EXTENDED_DATA_ID):
        if raw[i] == c.NIUSB_IBRD_DATA_ID:
            data_block_length = 0x0F
            i += 1
        else:
            data_block_length = 0x1E
            i += 1
            if raw[i] != 0:
                raise ValueError(f"unexpected extended readback byte at {i}: 0x{raw[i]:02x}")
            i += 1
        parsed.extend(raw[i : i + data_block_length])
        i += data_block_length
        num_data_blocks += 1

    status = parse_status_block(raw, i)
    i += 8
    if status.id != c.NIUSB_IBRD_STATUS_ID:
        raise ValueError(f"readback status id 0x{status.id:02x} != 0x{c.NIUSB_IBRD_STATUS_ID:02x}")

    i += 1
    if num_data_blocks:
        actual_length = (num_data_blocks - 1) * data_block_length + raw[i]
        i += 1
    else:
        actual_length = 0
        i += 1

    if raw[i : i + 2] != b"\x00\x00":
        raise ValueError(f"unexpected readback padding at {i}: {raw[i:i+2].hex(' ')}")
    i += 2

    register_write_status = parse_status_block(raw, i)
    i += 8
    if register_write_status.id != c.NIUSB_REG_WRITE_ID:
        raise ValueError(
            f"readback register-write status id 0x{register_write_status.id:02x} "
            f"!= 0x{c.NIUSB_REG_WRITE_ID:02x}"
        )
    if raw[i] != 2:
        raise ValueError(f"readback register-write count {raw[i]} != 2")
    i += 1
    if raw[i : i + 3] != b"\x00\x00\x00":
        raise ValueError(f"unexpected register-write padding at {i}: {raw[i:i+3].hex(' ')}")
    i += 3
    i += parse_termination_block(raw, i)
    return Readback(
        data=bytes(parsed[: min(actual_length, parsed_data_length)]),
        status=status,
        register_write_status=register_write_status,
        consumed=i,
        actual_length=actual_length,
    )


def _self_test() -> None:
    init_writes = build_init_writes()
    assert len(init_writes) == 26
    assert build_register_write(init_writes).startswith(bytes((0x09, 26, 0, 3, 0x10, 0)))
    assert build_command(bytes((c.UNL, mta(0), mla(19))), timeout_usec=1_000_000) == bytes.fromhex(
        "0c fd 00 fb 3f 40 33 00 04 00 00 00"
    )
    assert build_write(b"*IDN?", timeout_usec=1_000_000) == bytes.fromhex(
        "0d fb ff fb 00 00 08 00 2a 49 44 4e 3f 00 00 00 04 00 00 00"
    )
    assert build_read(1024, timeout_usec=1_000_000).startswith(bytes.fromhex("0a 00 00 fb 00 fc 00 00"))


if __name__ == "__main__":
    _self_test()
    print("niusbhs.protocol self-test passed")
