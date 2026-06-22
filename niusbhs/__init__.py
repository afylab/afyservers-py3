# SPDX-License-Identifier: GPL-2.0-or-later
#
# PyVISA-compatible userspace driver facade for NI GPIB-USB-HS.

from __future__ import annotations

import os
import re
import time
import threading
from dataclasses import dataclass
from typing import Iterable

from . import constants as c
from .protocol import (
    StatusBlock,
    build_command,
    build_go_to_standby,
    build_init_writes,
    build_interface_clear,
    build_read,
    build_register_write,
    build_take_control,
    build_write,
    mla,
    mta,
    parse_ibrd_readback,
    parse_reg_write_status_block,
    parse_status_block,
    timeout_msecs,
)


class NIUSBError(IOError):
    def __init__(self, message: str, status: StatusBlock | None = None, raw: bytes | None = None):
        self.status = status
        self.raw = raw
        if status is not None:
            message = (
                f"{message}: status id=0x{status.id:02x} ibsta=0x{status.ibsta:04x} "
                f"error_code={status.error_code} ({status.error_name}) count={status.count}"
            )
        super().__init__(message)


class ResourceNameError(ValueError):
    pass


@dataclass(frozen=True)
class DebugRecord:
    label: str
    out_hex: str
    in_hex: str
    status: StatusBlock | None


class NIUSBHS:
    def __init__(
        self,
        *,
        board_pad: int = 0,
        timeout: int = 1000,
        debug: bool | None = None,
        backend=None,
    ):
        self.board_pad = board_pad
        self.sad = -1
        self.master = True
        self.timeout = timeout
        self.eos_char = 0
        self.eos_mode = 0
        self.debug = _env_flag("NIUSBHS_DEBUG") if debug is None else debug
        self.backend = backend
        self.dev = None
        self.product_id = None
        self.interface = 0
        self.bulk_out_endpoint = c.NIUSB_HS_BULK_OUT_ENDPOINT
        self.bulk_in_endpoint = c.NIUSB_HS_BULK_IN_ENDPOINT
        self.interrupt_in_endpoint = c.NIUSB_HS_INTERRUPT_IN_ENDPOINT
        self.last_debug: list[DebugRecord] = []
        self._lock = threading.RLock()

    def open(self) -> "NIUSBHS":
        if self.dev is not None:
            return self
        try:
            import usb.core
            import usb.util
            import usb.backend.libusb1
        except ImportError as exc:
            raise NIUSBError("PyUSB is required; install pyusb and libusb") from exc

        backend = self.backend if self.backend is not None else usb.backend.libusb1.get_backend()
        dev = usb.core.find(idVendor=c.USB_VENDOR_ID_NI, idProduct=c.USB_DEVICE_ID_NI_USB_HS, backend=backend)
        if dev is None:
            dev = usb.core.find(
                idVendor=c.USB_VENDOR_ID_NI,
                idProduct=c.USB_DEVICE_ID_NI_USB_HS_PLUS,
                backend=backend,
            )
        if dev is None:
            raise NIUSBError("NI GPIB-USB-HS/HS+ was not found by PyUSB")

        dev.set_configuration()
        usb.util.claim_interface(dev, self.interface)
        self.dev = dev
        self.product_id = dev.idProduct
        if self.product_id == c.USB_DEVICE_ID_NI_USB_HS_PLUS:
            self.bulk_out_endpoint = c.NIUSB_HS_PLUS_BULK_OUT_ENDPOINT
            self.bulk_in_endpoint = c.NIUSB_HS_PLUS_BULK_IN_ENDPOINT
            self.interrupt_in_endpoint = c.NIUSB_HS_PLUS_INTERRUPT_IN_ENDPOINT
        self._load_endpoints_from_descriptors()
        self._hs_wait_for_ready()
        if self.product_id == c.USB_DEVICE_ID_NI_USB_HS_PLUS:
            self._hs_plus_extra_init()
        self.init()
        self.interface_clear()
        return self

    def close(self) -> None:
        if self.dev is None:
            return
        try:
            import usb.util

            usb.util.release_interface(self.dev, self.interface)
            usb.util.dispose_resources(self.dev)
        finally:
            self.dev = None

    def init(self) -> StatusBlock:
        status = self._register_write(build_init_writes(pad=self.board_pad, sad=self.sad, master=self.master))
        if status.id != c.NIUSB_REG_WRITE_ID or status.error_code != c.NIUSB_NO_ERROR:
            raise NIUSBError("init register-write failed", status)
        return status

    def clear(self, pad: int | None = None) -> None:
        if pad is None:
            self.interface_clear()
            return
        self._take_control(synchronous=True)
        self._command(bytes((c.UNL, mla(pad), c.SDC)))

    def interface_clear(self) -> StatusBlock:
        raw = self._bulk_transaction("ibsic", build_interface_clear(), 0x10, 1000, expected_in=12)
        status = parse_status_block(raw)
        self._raise_for_status("interface clear", status, raw)
        return status

    def write_to(self, pad: int, data: bytes | str, *, send_eoi: bool = True) -> int:
        payload = data.encode() if isinstance(data, str) else bytes(data)
        with self._lock:
            self._address_for_write(pad)
            return self._board_write(payload, send_eoi=send_eoi)

    def read_from(self, pad: int, count: int | None = None) -> bytes:
        with self._lock:
            self._address_for_read(pad)
            return self._board_read_until_end(count)

    def query(self, pad: int, data: bytes | str) -> bytes:
        with self._lock:
            self.write_to(pad, data)
            return self.read_from(pad)

    def scan(self, addresses: Iterable[int] | None = None, *, idn_query: bool = False) -> tuple[int, ...]:
        if addresses is None:
            env = _parse_addresses(os.environ.get("NIUSBHS_ADDRESSES"))
            if env:
                return tuple(env)
            addresses = range(31)
        found: list[int] = []
        for pad in addresses:
            try:
                if idn_query:
                    if self.query(pad, "*IDN?"):
                        found.append(pad)
                else:
                    self._address_for_write(pad)
                    found.append(pad)
            except Exception:
                continue
        return tuple(found)

    def _load_endpoints_from_descriptors(self) -> None:
        assert self.dev is not None
        try:
            cfg = self.dev.get_active_configuration()
            intf = cfg[(self.interface, 0)]
            bulk_out = []
            bulk_in = []
            interrupt_in = []
            for ep in intf:
                bm_attr = ep.bmAttributes & 0x03
                addr = ep.bEndpointAddress
                if bm_attr == 0x02 and addr & 0x80:
                    bulk_in.append(addr)
                elif bm_attr == 0x02:
                    bulk_out.append(addr)
                elif bm_attr == 0x03 and addr & 0x80:
                    interrupt_in.append(addr)
            if bulk_out:
                self.bulk_out_endpoint = bulk_out[0]
            if bulk_in:
                self.bulk_in_endpoint = bulk_in[0]
            if interrupt_in:
                self.interrupt_in_endpoint = interrupt_in[0]
            if self.debug:
                print(
                    "niusbhs endpoints "
                    f"bulk_out=0x{self.bulk_out_endpoint:02x} "
                    f"bulk_in=0x{self.bulk_in_endpoint:02x} "
                    f"interrupt_in=0x{self.interrupt_in_endpoint:02x}"
                )
        except Exception as exc:
            if self.debug:
                print(f"niusbhs endpoint descriptor read failed: {exc!r}; using HS defaults")

    def _control_read(
        self,
        label: str,
        request: int,
        request_type: int,
        value: int,
        index: int,
        length: int,
        timeout: int,
    ) -> bytes:
        if self.dev is None:
            raise NIUSBError("device is not open")
        raw = bytes(self.dev.ctrl_transfer(request_type, request, value, index, length, timeout=timeout))
        if self.debug:
            print(f"niusbhs {label} CTRL request=0x{request:02x} IN {raw.hex(' ')}")
        return raw

    def _hs_wait_for_ready(self) -> None:
        vendor_device_in = 0xC0
        serial = self._control_read(
            "serial",
            c.NI_USB_SERIAL_NUMBER_REQUEST,
            vendor_device_in,
            0,
            0,
            0x10,
            1000,
        )
        if not serial or serial[0] != c.NI_USB_SERIAL_NUMBER_REQUEST:
            raise NIUSBError(f"unexpected serial-number control reply: {serial.hex(' ')}")
        last = b""
        for _ in range(50):
            raw = self._control_read(
                "poll_ready",
                c.NI_USB_POLL_READY_REQUEST,
                vendor_device_in,
                0,
                0,
                0x10,
                100,
            )
            last = raw
            if len(raw) > 10 and raw[0] == c.NI_USB_POLL_READY_REQUEST and raw[10] != 0:
                return
            if (
                self.product_id == c.USB_DEVICE_ID_NI_USB_HS_PLUS
                and len(raw) > 9
                and raw[0] == c.NI_USB_POLL_READY_REQUEST
                and raw[9] == 0x30
            ):
                if self.debug:
                    print("niusbhs poll_ready did not set byte 10 on HS+; proceeding after valid init probe pattern")
                return
            time.sleep(0.1)
        if (
            self.product_id == c.USB_DEVICE_ID_NI_USB_HS_PLUS
            and len(last) > 9
            and last[0] == c.NI_USB_POLL_READY_REQUEST
            and last[9] == 0x30
        ):
            if self.debug:
                print("niusbhs poll_ready did not set byte 10 on HS+; proceeding after valid init probe pattern")
            return
        raise NIUSBError("adapter did not become ready after NI_USB_POLL_READY_REQUEST")

    def _hs_plus_extra_init(self) -> None:
        vendor_device_in = 0xC0
        vendor_interface_in = 0xC1
        checks = (
            ("hs_plus_0x48", c.NI_USB_HS_PLUS_0x48_REQUEST, vendor_device_in, 0, 0, 16),
            ("hs_plus_led", c.NI_USB_HS_PLUS_LED_REQUEST, vendor_device_in, 1, 0, 2),
            ("hs_plus_0xf8", c.NI_USB_HS_PLUS_0xF8_REQUEST, vendor_interface_in, 0, 1, 9),
        )
        for label, request, request_type, value, index, length in checks:
            raw = self._control_read(label, request, request_type, value, index, length, 1000)
            if not raw or raw[0] != request:
                raise NIUSBError(f"unexpected {label} control reply: {raw.hex(' ')}")

    def _register_write(self, registers) -> StatusBlock:
        raw = self._bulk_transaction(
            "register_write",
            build_register_write(registers),
            0x20,
            1000,
            expected_in=16,
        )
        status, writes_completed, consumed = parse_reg_write_status_block(raw)
        if consumed != 12:
            raise NIUSBError(f"unexpected register-write status length {consumed}", status, raw)
        if status.id != c.NIUSB_REG_WRITE_ID:
            raise NIUSBError("register-write reply id mismatch", status, raw)
        if status.error_code:
            raise NIUSBError("register-write returned nonzero error", status, raw)
        if writes_completed != len(tuple(registers)):
            raise NIUSBError(f"register-write completed {writes_completed} writes", status, raw)
        return status

    def _take_control(self, *, synchronous: bool) -> StatusBlock:
        raw = self._bulk_transaction(
            "ibcac",
            build_take_control(synchronous=synchronous),
            0x10,
            1000,
            expected_in=12,
        )
        status = parse_status_block(raw)
        self._raise_for_status("take control", status, raw)
        return status

    def _go_to_standby(self) -> StatusBlock:
        raw = self._bulk_transaction("ibgts", build_go_to_standby(), 0x20, 1000, expected_in=12)
        status = parse_status_block(raw)
        self._raise_for_status("go to standby", status, raw)
        return status

    def _command(self, data: bytes) -> int:
        written = 0
        while written < len(data):
            chunk = data[written : written + 0x10]
            raw = self._bulk_transaction(
                "command",
                build_command(chunk, timeout_usec=self.timeout * 1000),
                0x10,
                _transfer_timeout_ms(self.timeout),
                expected_in=12,
            )
            status = parse_status_block(raw)
            self._raise_for_status("command", status, raw)
            completed = len(chunk) - status.count
            if completed <= 0 and status.count:
                raise NIUSBError("command made no progress", status, raw)
            written += completed
        return written

    def _address_for_write(self, pad: int) -> None:
        self._take_control(synchronous=True)
        self._command(bytes((c.UNL, mta(self.board_pad), mla(pad))))
        self._go_to_standby()

    def _address_for_read(self, pad: int) -> None:
        self._take_control(synchronous=True)
        self._command(bytes((c.UNL, mla(self.board_pad), mta(pad))))
        self._go_to_standby()

    def _board_write(self, payload: bytes, *, send_eoi: bool) -> int:
        if not payload:
            return 0
        raw = self._bulk_transaction(
            "write",
            build_write(payload, send_eoi=send_eoi, timeout_usec=self.timeout * 1000),
            0x10,
            _transfer_timeout_ms(self.timeout),
            expected_in=12,
        )
        status = parse_status_block(raw)
        self._raise_for_status("write", status, raw)
        return len(payload) - status.count

    def _board_read_until_end(self, count: int | None) -> bytes:
        target = count if count is not None else 4096
        chunks: list[bytes] = []
        remaining = target
        while remaining > 0:
            request_len = min(remaining, 0xFFFF)
            data, status = self._board_read_once(request_len)
            chunks.append(data)
            if status.ibsta & c.END:
                break
            if not data:
                break
            if count is None:
                remaining = 4096
            else:
                remaining -= len(data)
        return b"".join(chunks)

    def _board_read_once(self, length: int) -> tuple[bytes, StatusBlock]:
        in_len = (length // 30 + 1) * 0x20 + 0x20
        raw = self._bulk_transaction(
            "read",
            build_read(
                length,
                eos_mode=self.eos_mode,
                eos_char=self.eos_char,
                timeout_usec=self.timeout * 1000,
            ),
            in_len,
            _transfer_timeout_ms(self.timeout),
        )
        readback = parse_ibrd_readback(raw, parsed_data_length=length)
        if self.debug:
            print(
                "niusbhs read READBACK "
                f"id=0x{readback.status.id:02x} ibsta=0x{readback.status.ibsta:04x} "
                f"error_code={readback.status.error_code} count={readback.status.count} "
                f"actual_length={readback.actual_length}"
            )
            print(
                "niusbhs read REGWRITE "
                f"id=0x{readback.register_write_status.id:02x} "
                f"ibsta=0x{readback.register_write_status.ibsta:04x} "
                f"error_code={readback.register_write_status.error_code} "
                f"count={readback.register_write_status.count}"
            )
        self._raise_for_status("read", readback.status, raw)
        return readback.data, readback.status

    def _bulk_transaction(
        self,
        label: str,
        out_data: bytes,
        in_length: int,
        timeout_ms: int,
        *,
        expected_in: int | None = None,
    ) -> bytes:
        if self.dev is None:
            raise NIUSBError("device is not open")
        written = self.dev.write(self.bulk_out_endpoint, out_data, timeout=timeout_ms)
        if written != len(out_data):
            raise NIUSBError(f"{label} wrote {written} bytes, expected {len(out_data)}")
        raw = bytes(self.dev.read(self.bulk_in_endpoint, in_length, timeout=timeout_ms))
        status = None if label == "read" else parse_status_block(raw) if len(raw) >= 8 else None
        self._record_debug(label, out_data, raw, status)
        if expected_in is not None and len(raw) != expected_in:
            raise NIUSBError(f"{label} read {len(raw)} bytes, expected {expected_in}", status, raw)
        return raw

    def _record_debug(self, label: str, out_data: bytes, raw: bytes, status: StatusBlock | None) -> None:
        record = DebugRecord(label, out_data.hex(" "), raw.hex(" "), status)
        self.last_debug.append(record)
        if len(self.last_debug) > 100:
            del self.last_debug[:-100]
        if self.debug:
            print(f"niusbhs {label} OUT {record.out_hex}")
            print(f"niusbhs {label} IN  {record.in_hex}")
            if status is not None:
                print(
                    f"niusbhs {label} STATUS id=0x{status.id:02x} "
                    f"ibsta=0x{status.ibsta:04x} error_code={status.error_code} count={status.count}"
                )

    @staticmethod
    def _raise_for_status(label: str, status: StatusBlock, raw: bytes | None = None) -> None:
        if status.error_code != c.NIUSB_NO_ERROR:
            raise NIUSBError(f"{label} returned NIUSB error", status, raw)


class USBInstrument:
    def __init__(self, bus: NIUSBHS, pad: int):
        self.bus = bus
        self.pad = pad
        self.timeout = bus.timeout
        self.write_termination = ""
        self.read_termination = ""

    def clear(self) -> None:
        self.bus.timeout = self.timeout
        self.bus.clear(self.pad)

    def write(self, data: str) -> int:
        payload = data
        if self.write_termination and not payload.endswith(self.write_termination):
            payload += self.write_termination
        self.bus.timeout = self.timeout
        return self.bus.write_to(self.pad, payload)

    def write_raw(self, data: bytes | bytearray) -> int:
        self.bus.timeout = self.timeout
        return self.bus.write_to(self.pad, bytes(data))

    def read_raw(self, size: int | None = None) -> bytes:
        self.bus.timeout = self.timeout
        data = self.bus.read_from(self.pad, size)
        if self.read_termination:
            term = self.read_termination.encode()
            if data.endswith(term):
                data = data[: -len(term)]
        return data

    def read(self) -> str:
        return self.read_raw().decode(errors="replace")

    def query(self, data: str) -> str:
        self.write(data)
        return self.read()

    def close(self) -> None:
        pass


class ResourceManager:
    def __init__(self, *args, **kwargs):
        del args, kwargs
        self._bus = NIUSBHS()
        self._resources = _parse_addresses(os.environ.get("NIUSBHS_ADDRESSES"))

    def list_resources(self, query: str | None = None) -> tuple[str, ...]:
        del query
        addrs = self._resources
        if not addrs and not _env_flag("NIUSBHS_NO_SCAN"):
            self._bus.open()
            addrs = self._bus.scan(idn_query=not _env_flag("NIUSBHS_ADDRESS_ONLY_SCAN"))
            self._resources = addrs
        return tuple(f"GPIB0::{pad}::INSTR" for pad in addrs)

    def scan(self, addresses: Iterable[int] | None = None) -> tuple[int, ...]:
        self._bus.open()
        return self._bus.scan(addresses)

    def open_resource(self, resource_name: str) -> USBInstrument:
        pad = _parse_resource_name(resource_name)
        self._bus.open()
        return USBInstrument(self._bus, pad)

    def close(self) -> None:
        self._bus.close()


def _parse_resource_name(resource_name: str) -> int:
    match = re.fullmatch(r"GPIB\d+::(\d+)::INSTR", resource_name.strip(), re.IGNORECASE)
    if not match:
        raise ResourceNameError(f"unsupported NIUSBHS resource name: {resource_name!r}")
    pad = int(match.group(1))
    if not 0 <= pad <= 30:
        raise ResourceNameError(f"GPIB primary address out of range: {pad}")
    return pad


def _parse_addresses(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    parts = re.split(r"[\s,;:]+", value.strip())
    addresses = []
    for part in parts:
        if not part:
            continue
        pad = int(part, 0)
        if not 0 <= pad <= 30:
            raise ValueError(f"NIUSBHS_ADDRESSES contains out-of-range address {pad}")
        addresses.append(pad)
    return tuple(dict.fromkeys(addresses))


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _transfer_timeout_ms(timeout_ms: int) -> int:
    return timeout_msecs(timeout_ms * 1000) or 0


__all__ = [
    "NIUSBHS",
    "NIUSBError",
    "ResourceManager",
    "ResourceNameError",
    "StatusBlock",
]
