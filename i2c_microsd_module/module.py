# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""module — async file core + legacy queries (port of the I²C microSD Expansion Arduino host library).

Transport mirrors the C++ library verbatim:

* repeated-START reads (``writeto_then_readfrom`` — never STOP between
  command and read; module discards the command on STOP),
* ACK is not committed (``opDone``/``result`` latch),
* flow-paced writes (``rxFree``-guided, 0 blind retries),
* ``CLOSE_FLUSH`` barrier on open after any gap > 4 s (abrupt host loss),
* 6x open retry, first barrier unconditional.

Split into :class:`I2CmicroSD` (address/sentinel) and :class:`MicroSDExpFile`.
Solved for CircuitPython: ``busio.I2C`` + ``I2CDevice`` locking; sketch owns
pin creation (like ``Wire.begin()`` on Arduino).
"""

import time

from . import config, protocol


# ---- Non-blocking API types ----------------------------------------------
ASYNC_IOERR = -2   # STATUS read failed
ASYNC_BUSY = -1    # operation not finished yet
ASYNC_OK = 0       # operation completed with no error

OP_OPEN_WRITE = 1
OP_OPEN_READ = 2
OP_CLOSE = 3
OP_FORMAT = 4
OP_QUERY = 5


class AsyncOp:
    """Token returned by a begin_*() call; pass to poll_op()."""
    __slots__ = ("done_before", "kind")

    def __init__(self):
        self.done_before = 0
        self.kind = 0


class MicroSDExpError:
    """Normalized module errors (mirror of the C++ enum).

    CircuitPython has no ``enum`` module — class ints keep the same
    member names so ported sketches read identically.
    """

    OK = 0
    NO_MODULE = 1
    NO_FILE = 2
    OPEN_FAIL = 3
    CARD_ERR = 4
    QUEUE_FULL = 5
    INVALID = 6
    OVERFLOW = 7
    TIMEOUT = 8


class _ErrorSlot:
    """Error attribute: last result plus first failure since clear_error().

    Internal library calls may overwrite ``last_error``; a real fault stays
    visible in ``sticky_error`` until the caller explicitly clears it.
    """

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return obj.__dict__.get("_last_error_value", MicroSDExpError.OK)

    def __set__(self, obj, value):
        obj.__dict__["_last_error_value"] = value
        if value != MicroSDExpError.OK:
            obj.__dict__["_sticky_error"] = value


class StatusFrame:
    """12-byte STATUS frame: rev, state, opDone, error, rxFree, txAvail, result."""

    __slots__ = ("rev", "state", "op_done", "error", "rx_free", "tx_avail", "result")

    def __init__(self):
        self.rev = 0
        self.state = 0
        self.op_done = 0
        self.error = 0
        self.rx_free = 0
        self.tx_avail = 0
        self.result = 0


class CardInfo:
    """24-byte CARD_INFO frame (all LE)."""

    __slots__ = (
        "mounted",
        "fat_type",
        "card_type",
        "sector_count",
        "free_clusters",
        "err_code",
        "err_data",
        "cluster_count",
        "sck_hz",
    )

    def __init__(self):
        self.mounted = 0
        self.fat_type = 0
        self.card_type = 0
        self.sector_count = 0
        self.free_clusters = 0
        self.err_code = 0
        self.err_data = 0
        self.cluster_count = 0
        self.sck_hz = 0

    @property
    def free_bytes(self):
        """Free bytes = free_clusters * sectors-per-cluster * 512 is device
        side; the module only reports free_clusters, so expose the raw
        cluster count and let the sketch multiply (clusters are usually
        32-64 sectors). Provided for API parity with the docs."""

    # Note: kept as method docs. Sketch computes free space from
    # sector_count/free_clusters/cluster_count + the card's bps/sectors.
    def __repr__(self):
        return (
            f"CardInfo(mounted={self.mounted}, fat={self.fat_type}, "
            f"sectors={self.sector_count}, free_clusters={self.free_clusters})"
        )


class DirEntry:
    """One listDir entry."""

    __slots__ = ("is_dir", "name", "size")

    def __init__(self, is_dir=False, name="", size=0):
        self.is_dir = is_dir
        self.name = name
        self.size = size

    def __repr__(self):
        kind = "D" if self.is_dir else "F"
        return f"{kind} {self.name!r} {self.size}"


# Expansion pin -> module command byte (the pair is per pin on the wire).
_PIN_IDS = (
    protocol.MICROSDEXP_PIN_PA5,
    protocol.MICROSDEXP_PIN_PB2,
    protocol.MICROSDEXP_PIN_PB3,
)
_PIN_MODE_CMD = {
    protocol.MICROSDEXP_PIN_PA5: protocol.MICROSDEXP_CMD_PA5_SET_MODE,
    protocol.MICROSDEXP_PIN_PB2: protocol.MICROSDEXP_CMD_PB2_SET_MODE,
    protocol.MICROSDEXP_PIN_PB3: protocol.MICROSDEXP_CMD_PB3_SET_MODE,
}
_PIN_CONTROL_CMD = {
    protocol.MICROSDEXP_PIN_PA5: protocol.MICROSDEXP_CMD_PA5_CONTROL,
    protocol.MICROSDEXP_PIN_PB2: protocol.MICROSDEXP_CMD_PB2_CONTROL,
    protocol.MICROSDEXP_PIN_PB3: protocol.MICROSDEXP_CMD_PB3_CONTROL,
}


def _le16(b, off):
    return b[off] | (b[off + 1] << 8)


def _le32(b, off):
    return b[off] | (b[off + 1] << 8) | (b[off + 2] << 16) | (b[off + 3] << 24)


def _diag_bytes(n):
    """Format a byte count like the ESP32 gateway's cardinfo."""
    return "%.1f MiB / %.2f GiB" % (n / 1048576.0, n / 1073741824.0)


class I2CmicroSD:
    """Host for the I²C microSD Expansion module (one open file at a time)."""

    # last_error is a descriptor so internal calls cannot erase a real fault.
    _last_error = _ErrorSlot()

    def __init__(self, i2c_device, scl_hz=400000, poll_ms=10, flow_poll_ms=2, address=config.DEFAULT_ADDRESS):
        """
        :param i2c_device: ``busio.I2C`` bus (wrapped automatically) or an
            ``adafruit_bus_device.i2c_device.I2CDevice`` for this module.
        :param scl_hz: configured I2C clock (for timeout scaling only —
            the bus carries its own frequency).
        :param poll_ms: STATUS poll pause.
        :param flow_poll_ms: rxFree re-check while write-blocked.
        :param address: 7-bit module address (used only when wrapping a bus).
        """
        self._bus = None
        if hasattr(i2c_device, "write_then_readinto"):
            # Already an I2CDevice — use as-is.
            self._device = i2c_device
            # Try to recover the bus handle for later re-addressing.
            for attr in ("i2c", "_i2c"):
                try:
                    self._bus = getattr(i2c_device, attr)
                    break
                except Exception:
                    continue
        else:
            # Raw busio.I2C — wrap it.
            from adafruit_bus_device import i2c_device as _dev_mod

            self._bus = i2c_device
            self._device = _dev_mod.I2CDevice(i2c_device, address, probe=False)
        self._device_address = address
        self._scl_hz = scl_hz
        self._poll_ms = poll_ms
        self._flow_poll_ms = flow_poll_ms
        self._read_chunk = config.READ_CHUNK_BYTES
        self._last_error = MicroSDExpError.OK
        self._file_open = False
        self._async_pending = False
        self._append_mode = False
        self._read_started = False
        self._base_written = 0
        self._written = 0
        self._last_active = 0.0
        self._append_path = ""
        # Last mode applied per expansion pin (None = "none yet"), so a
        # redundant set_pin_mode(pin, same) is a library-side no-op: no bus
        # transaction, no module EEPROM write.
        self._pin_last_mode = {pid: None for pid in _PIN_IDS}
        # Reusable staging (single-file module: no concurrency).
        self._shared = bytearray(128)

    # ---- helpers ----
    @classmethod
    def from_bus(cls, i2c, address=config.DEFAULT_ADDRESS, **kw):
        """Convenience: build the I2CDevice for you (bus stays sketch-owned)."""
        from adafruit_bus_device import i2c_device

        dev = i2c_device.I2CDevice(i2c, address, probe=False)
        return cls(dev, **kw)

    @property
    def scl_hz(self):
        return self._scl_hz

    @property
    def last_error(self):
        return self._last_error

    @property
    def last_ok(self):
        """True when the most recent call completed without error."""
        return self._last_error == MicroSDExpError.OK

    @property
    def sticky_error(self):
        """First error since clear_error(); OK if no failure was recorded."""
        return self.__dict__.get("_sticky_error", MicroSDExpError.OK)

    def clear_error(self):
        """Reset both last_error and sticky_error to OK."""
        self._last_error = MicroSDExpError.OK
        self.__dict__["_sticky_error"] = MicroSDExpError.OK

    @property
    def file_open(self):
        return self._file_open

    def set_poll_interval(self, ms):
        self._poll_ms = ms

    def set_read_chunk_bytes(self, n):
        """Bytes requested per READ drain, clamped to 1..256.

        Defaults to ``config.READ_CHUNK_BYTES`` (256, matching the v18.8.21
        firmware's two staged 128 B TX buffers). Lower it for a bus/port that
        cannot carry the full chunk in one transaction.
        """
        if n < 1:
            n = 1
        if n > 256:
            n = 256
        self._read_chunk = n

    def read_chunk_bytes(self):
        return self._read_chunk

    def scale_timeout(self, base_ms):
        """base * 100000/scl_hz, >= base, >= 2x below 50 kHz, cap 120 s."""
        if self._scl_hz == 0:
            return base_ms
        scaled = base_ms * 100000 // self._scl_hz
        if scaled < base_ms:
            scaled = base_ms
        if self._scl_hz < 50000:
            dbl = base_ms * 2
            if scaled < dbl:
                scaled = dbl
        if scaled > 120000:
            scaled = 120000
        return scaled

    # ---- transport ----
    def _write(self, payload):
        """Write payload then STOP. Returns True, or False on NACK."""
        self._last_active = time.monotonic()
        try:
            with self._device:
                self._device.write(payload)
            self._last_error = MicroSDExpError.OK
            return True
        except OSError:
            self._last_error = MicroSDExpError.NO_MODULE
            return False

    def _write_then_read(self, payload, n, out):
        """Repeated-START: write payload, immediately read n bytes into out[0:n].
        Returns bytes read (0 on bus error)."""
        self._last_active = time.monotonic()
        try:
            with self._device:
                self._device.write_then_readinto(payload, out, in_end=n)
            self._last_error = MicroSDExpError.OK
            return n
        except OSError:
            self._last_error = MicroSDExpError.NO_MODULE
            return 0

    def raw_write(self, cmd, data=b""):
        """Send a raw command + STOP transaction (advanced users).

        Returns True on ACK, False on NACK. Matches the reference implementation
        ``moduleSend(cmd, data, stop=true)``."""
        return self._write(bytes([cmd]) + bytes(data))

    def raw_read(self, cmd, n):
        """Repeated-START read of n bytes. Returns bytes (short on error)."""
        buf = bytearray(n)
        got = self._write_then_read(bytes([cmd]), n, buf)
        return bytes(buf[:got])

    def set_address(self, addr):
        """Switch to a new address (I2C_SET_ADDR tests).

        The CircuitPython built-in I2CDevice is immutable (no
        ``device_address`` attribute), so recreate the device object.
        """
        self._device_address = addr
        if self._bus is not None:
            try:
                from adafruit_bus_device import i2c_device as _dev_mod

                self._device = _dev_mod.I2CDevice(self._bus, addr, probe=False)
            except Exception:
                pass

    def read_status(self, st=None):
        """Read the 12-byte STATUS frame. Returns StatusFrame or None."""
        if st is None:
            st = StatusFrame()
        n = self._write_then_read(bytes([protocol.MICROSDEXP_CMD_STATUS]), 12, self._shared)
        if n < 12:
            return None
        b = self._shared
        st.rev = b[0]
        st.state = b[1]
        st.op_done = b[2]
        st.error = b[3]
        st.rx_free = _le16(b, 4)
        st.tx_avail = _le16(b, 6)
        st.result = _le32(b, 8)
        return st

    def wait_for_op_complete(self, done_before, timeout_ms=config.OP_TIMEOUT_MS, scale=True):
        """Poll STATUS until opDone != done_before.

        Returns ``status.error`` (0 = COMPLETE) or -1 on timeout. Set ``scale``
        to False when the caller already owns the budget (e.g. format())."""
        limit = (self.scale_timeout(timeout_ms) if scale else timeout_ms) / 1000.0
        t0 = time.monotonic()
        while (time.monotonic() - t0) < limit:
            st = self.read_status()
            if st is None:
                time.sleep(self._poll_ms / 1000.0)
                continue
            if st.op_done != done_before:
                self._last_error = MicroSDExpError.OK
                return st.error
            time.sleep(self._poll_ms / 1000.0)
        self._last_error = MicroSDExpError.TIMEOUT
        return -1

    def wait_for_committed(self, target, timeout_ms=config.COMMIT_TIMEOUT_MS):
        limit = self.scale_timeout(timeout_ms) / 1000.0
        t0 = time.monotonic()
        while (time.monotonic() - t0) < limit:
            st = self.read_status()
            if st is not None:
                if st.state == protocol.MICROSDEXP_ST_ERROR:
                    self._last_error = MicroSDExpError.CARD_ERR
                    return False
                if st.result >= target:
                    return True
            time.sleep(self._poll_ms / 1000.0)
        self._last_error = MicroSDExpError.TIMEOUT
        return False

    def begin(self):
        """Probe the module. The real address is read from STATUS rev.

        Address scan: bound device address first, then 0x6A-0x6F (the
        module's I2C_SET_ADDR live range) — keeps sketches honest about
        the 0x6E default, matching the Arduino library. Returns True on
        ACK of any module rev 2 STATUS.
        """
        st = self.read_status()
        if st is not None:
            self._last_error = MicroSDExpError.OK
            return True
        # Try alternate addresses 0x6A-0x6F (recreate device; CP I2CDevice
        # address is immutable, so mutate is not possible).
        saved = self._device_address
        for addr in range(0x6A, 0x70):
            if addr == saved:
                continue
            self.set_address(addr)
            if self.read_status() is not None:
                self._last_error = MicroSDExpError.OK
                return True
        self.set_address(saved)
        self._last_error = MicroSDExpError.NO_MODULE
        return False

    # ---- barriers ----
    def _barrier_close_flush(self):
        st = self.read_status()
        db = st.op_done if st is not None else 0
        if not self._write(bytes([protocol.MICROSDEXP_CMD_CLOSE_FLUSH])):
            return False
        return self.wait_for_op_complete(db) == 0

    def _barrier_if_gap(self):
        if (time.monotonic() - self._last_active) > 4.0:
            self._barrier_close_flush()

    # ---- paths ----
    def valid_path(self, path):
        """Length-gate only (module handles LFN semantics).

        Invalid: None/empty/overlong (no I2C sent)."""
        if not path or len(path) == 0 or len(path) >= config.PATH_MAX:
            self._last_error = MicroSDExpError.INVALID
            return False
        return True

    def _submit_filename(self, path):
        if not self.valid_path(path):
            return False
        try:
            data = path.encode("ascii") + b"\x00"
        except (UnicodeEncodeError, AttributeError):
            self._last_error = MicroSDExpError.INVALID
            return False
        if len(data) > config.PATH_MAX:
            self._last_error = MicroSDExpError.INVALID
            return False
        return self._write(bytes([protocol.MICROSDEXP_CMD_FILENAME]) + data)

    def _legacy_op(self, cmd, path, want_result=False):
        """doneBefore -> 0x01 -> cmd -> wait -> STATUS.result latch."""
        st = self.read_status()
        done_before = st.op_done if st is not None else 0
        if not self._submit_filename(path):
            return (100, 0)
        if not self._write(bytes([cmd])):
            return (101, 0)
        err = self.wait_for_op_complete(done_before)
        if err < 0:
            self._last_error = MicroSDExpError.TIMEOUT
            return (err, 0)
        result = 0
        if want_result:
            st2 = self.read_status()
            result = st2.result if st2 is not None else 0
        if err != 0:
            self._last_error = MicroSDExpError.OPEN_FAIL if err == protocol.MICROSDEXP_ERR_OPEN else MicroSDExpError.CARD_ERR
        else:
            self._last_error = MicroSDExpError.OK
        return (err, result)

    # ---- legacy queries + dirs ----
    def mkdir(self, path):
        if not self.valid_path(path):
            return False
        return self._legacy_op(protocol.MICROSDEXP_CMD_MAKE_DIR, path)[0] == 0

    def rmdir(self, path):
        if not self.valid_path(path):
            return False
        return self._legacy_op(protocol.MICROSDEXP_CMD_REMOVE_DIR, path)[0] == 0

    def remove(self, path):
        if not self.valid_path(path):
            return False
        return self._legacy_op(protocol.MICROSDEXP_CMD_REMOVE_FILE, path)[0] == 0

    def exists_checked(self, path):
        """Return (ok, exists). ``ok`` is False on I2C/card/path error."""
        if not self.valid_path(path):
            return (False, False)
        err, res = self._legacy_op(protocol.MICROSDEXP_CMD_FILE_EXISTS, path, want_result=True)
        return (err == 0, err == 0 and res == 1)

    def exists(self, path):
        """True if the path exists. On error returns False — check last_ok."""
        return self.exists_checked(path)[1]

    def file_size_checked(self, path):
        """Return (ok, size_bytes). ``ok`` distinguishes 0 bytes from an error."""
        if not self.valid_path(path):
            return (False, 0)
        err, res = self._legacy_op(protocol.MICROSDEXP_CMD_FILE_SIZE, path, want_result=True)
        return (err == 0, res if err == 0 else 0)

    def file_size(self, path):
        """Size in bytes, 0 if not found or on error — check last_ok."""
        return self.file_size_checked(path)[1]

    def is_directory_checked(self, path):
        """Return (ok, is_directory). ``ok`` is False on error."""
        if not self.valid_path(path):
            return (False, False)
        err, res = self._legacy_op(protocol.MICROSDEXP_CMD_IS_DIRECTORY, path, want_result=True)
        return (err == 0, err == 0 and res == 1)

    def is_directory(self, path):
        """True if the path is a directory — check last_ok on error."""
        return self.is_directory_checked(path)[1]

    def firmware_banner(self):
        """Full identification banner returned by CMD_VERSION (0x0F).

        Firmware >= 18.8.0 answers with a multi-line banner whose first line is
        the measured clock, not the version::

            Clock: 20000000 Hz (fuse OSCCFG=0x7E)
            I2C microSD Expansion v18.8.22
            Copyright (C) 2026 syntax1269@gmail.com

        Older firmware answers with the bare version string ("18.7.6").
        """
        buf = bytearray(config.VERSION_BANNER_BYTES)
        n = self._write_then_read(bytes([protocol.MICROSDEXP_CMD_VERSION]),
                                  config.VERSION_BANNER_BYTES, buf)
        if n == 0:
            return ""
        end = 0
        while end < n and buf[end] != 0:
            end += 1
        self._last_error = MicroSDExpError.OK
        return bytes(buf[:end]).decode("ascii", "replace").strip()

    def version(self):
        """Firmware version string (e.g. "18.8.22"), or "" on error.

        Accepts both the bare string of firmware <= 18.7.x and the banner of
        firmware >= 18.8.0 (where the first line is the clock).
        """
        text = self.firmware_banner()
        for raw in text.split():
            token = raw.strip("(),;")
            if token[:1] in ("v", "V"):
                token = token[1:]
            parts = token.split(".")
            if len(parts) >= 2 and all(part.isdigit() for part in parts):
                return token
        # No dotted token: banner truncated by the buffer or malformed.
        self._last_error = MicroSDExpError.INVALID
        return ""

    def firmware_clock_hz(self):
        """Clock the module measured at power-up (firmware >= 18.8.0), else 0."""
        for line in self.firmware_banner().splitlines():
            line = line.strip()
            if line.lower().startswith("clock:"):
                for part in line.replace(":", " ").replace("(", " ").split():
                    if part.isdigit():
                        return int(part)
        return 0

    def temperature_k(self):
        """Die temperature in whole kelvin (2-byte LE); 0xFFFF on error."""
        buf = bytearray(2)
        if self._write_then_read(bytes([protocol.MICROSDEXP_CMD_TEMP_READ]), 2, buf) < 2:
            self._last_error = MicroSDExpError.INVALID
            return 0xFFFF
        self._last_error = MicroSDExpError.OK
        return _le16(buf, 0)

    def adc_pa5(self):
        """Raw 12-bit ADC word from PA5; 0xFFFF on error/unavailable channel."""
        buf = bytearray(3)
        if self._write_then_read(bytes([protocol.MICROSDEXP_CMD_ADC_READ_PA5]), 3, buf) < 2:
            self._last_error = MicroSDExpError.INVALID
            return 0xFFFF
        if buf[0] == 0xFF and buf[1] == 0xFF:
            self._last_error = MicroSDExpError.INVALID
            return 0xFFFF
        self._last_error = MicroSDExpError.OK
        return _le16(buf, 0)

    def card_info(self):
        """24-byte CARD_INFO snapshot as CardInfo, or None."""
        buf = bytearray(24)
        if self._write_then_read(bytes([protocol.MICROSDEXP_CMD_CARD_INFO]), 24, buf) < 24:
            self._last_error = MicroSDExpError.INVALID
            return None
        out = CardInfo()
        out.mounted = buf[0]
        out.fat_type = buf[1]
        out.card_type = buf[2]
        out.sector_count = _le32(buf, 4)
        out.free_clusters = _le32(buf, 8)
        out.err_code = _le16(buf, 12)
        out.err_data = _le16(buf, 14)
        out.cluster_count = _le32(buf, 16)
        out.sck_hz = _le32(buf, 20)
        self._last_error = MicroSDExpError.OK
        return out

    def diagnostics(self):
        """Return a one-page health report for troubleshooting.

        Reports module presence, firmware and protocol version, card/filesystem
        state, capacity and free space, the bound I²C address, the configured
        bus clock and a communication verdict. Safe to call before ``begin()``:
        fields that could not be read are shown as ``n/a``. The call does not
        change :attr:`last_error`.

        Free space uses the module's ``free_clusters`` value; a reported 0 means
        unknown (scan pending) or a full card, so the report says ``unknown``.
        """
        preserved = self._last_error
        lines = ["I2C microSD Expansion", "---------------------"]
        st = self.read_status()
        lines.append("Module detected:   %s" % ("yes" if st is not None else "no"))
        lines.append("Protocol version:  %s" % (str(st.rev) if st is not None else "n/a"))

        fw = self.version()
        lines.append("Firmware version:  %s" % (fw if fw else "unknown"))

        ci = self.card_info()
        lines.append("SD card detected:  %s" % ("yes" if ci is not None and ci.mounted else "no"))
        if ci is not None:
            fat_names = {12: "FAT12", 16: "FAT16", 32: "FAT32", 64: "exFAT"}
            lines.append("Filesystem:        %s" % fat_names.get(ci.fat_type, "unknown"))
            capacity = ci.sector_count * 512
            lines.append("Capacity:          %s" % (
                _diag_bytes(capacity) if capacity else "n/a"))
            if ci.cluster_count > 0 and ci.free_clusters > 0:
                cluster = ((capacity // ci.cluster_count + 256) // 512) * 512
                lines.append("Free space:        %s" % _diag_bytes(ci.free_clusters * cluster))
            elif ci.free_clusters == 0:
                lines.append("Free space:        unknown")
            else:
                lines.append("Free space:        n/a")
        else:
            lines.extend(["Filesystem:        n/a",
                          "Capacity:          n/a",
                          "Free space:        n/a"])

        lines.append("I2C address:       0x%02X" % self._device_address)
        lines.append("I2C speed:         %d kHz (configured)" % (self._scl_hz // 1000))
        lines.append("Communication:     %s" % (
            "OK" if st is not None and st.error == 0 else "CHECK"))

        self._last_error = preserved
        return "\n".join(lines)

    # ---- Non-blocking API (no sleeps; call from your loop) -----------------
    def _async_submit_open(self, cmd, path, op, kind):
        if self._async_pending or not self.valid_path(path):
            return False
        st = self.read_status()
        if st is None:
            self._last_error = MicroSDExpError.NO_MODULE
            return False
        try:
            raw = path.encode("ascii") + b"\x00"
        except (UnicodeEncodeError, AttributeError):
            self._last_error = MicroSDExpError.INVALID
            return False
        if not self._write(bytes([cmd]) + raw):
            return False
        op.done_before = st.op_done
        op.kind = kind
        self._async_pending = True
        self._append_mode = False
        self._read_started = False
        self._written = 0
        self._file_open = kind in (OP_OPEN_WRITE, OP_OPEN_READ)
        self._last_error = MicroSDExpError.OK
        return True

    def begin_open_write(self, path, op):
        """Submit OPEN_WRITE without waiting; poll with poll_op()."""
        return self._async_submit_open(protocol.MICROSDEXP_CMD_OPEN_WRITE, path, op, OP_OPEN_WRITE)

    def begin_open_read(self, path, op):
        """Submit OPEN_READ without waiting; poll with poll_op()."""
        return self._async_submit_open(protocol.MICROSDEXP_CMD_OPEN_READ, path, op, OP_OPEN_READ)

    def begin_close(self, op):
        """Submit CLOSE_FLUSH without waiting; poll with poll_op()."""
        if self._async_pending or not self._file_open:
            return False
        if self._append_mode:  # append chunks are atomic; no module op
            self._file_open = False
            self._append_mode = False
            self._read_started = False
            self._last_error = MicroSDExpError.OK
            return False
        st = self.read_status()
        if st is None:
            self._last_error = MicroSDExpError.NO_MODULE
            return False
        if not self._write(bytes([protocol.MICROSDEXP_CMD_CLOSE_FLUSH])):
            return False
        op.done_before = st.op_done
        op.kind = OP_CLOSE
        self._async_pending = True
        return True

    def begin_format(self, mode, op):
        """Submit FORMAT without waiting (destructive)."""
        if mode not in (0, 1) or self._async_pending:
            self._last_error = MicroSDExpError.INVALID
            return False
        st = self.read_status()
        if st is None:
            self._last_error = MicroSDExpError.NO_MODULE
            return False
        if not self._write(bytes([protocol.MICROSDEXP_CMD_FORMAT, mode])):
            return False
        op.done_before = st.op_done
        op.kind = OP_FORMAT
        self._async_pending = True
        return True

    def begin_query(self, cmd, path, op):
        """Submit a queued command (optionally with a path) without waiting."""
        if self._async_pending:
            return False
        st = self.read_status()
        if st is None:
            self._last_error = MicroSDExpError.NO_MODULE
            return False
        if path and not self._submit_filename(path):
            return False
        if not self._write(bytes([cmd])):
            return False
        op.done_before = st.op_done
        op.kind = OP_QUERY
        self._async_pending = True
        return True

    def poll_op(self, op):
        """One STATUS read: ASYNC_BUSY, ASYNC_OK, module error, or ASYNC_IOERR."""
        st = self.read_status()
        if st is None:
            return ASYNC_IOERR
        if st.op_done == op.done_before:
            return ASYNC_BUSY
        if not self._async_pending:
            return st.error
        self._async_pending = False
        if op.kind == OP_OPEN_WRITE:
            self._base_written = st.result
        elif op.kind == OP_OPEN_READ:
            self._base_written = st.result
            self._write(bytes([protocol.MICROSDEXP_CMD_READ]))  # prime the stream
            self._read_started = True
        elif op.kind == OP_CLOSE:
            self._file_open = False
            self._read_started = False
        if st.error == 0:
            self._last_error = MicroSDExpError.OK
        else:
            self._last_error = (MicroSDExpError.OPEN_FAIL
                                if st.error == protocol.MICROSDEXP_ERR_OPEN
                                else MicroSDExpError.CARD_ERR)
        return st.error

    def write_now(self, data):
        """Push at most one chunk if RX has room now. Returns bytes accepted."""
        if not data or not self._file_open or self._async_pending:
            if not self._file_open:
                self._last_error = MicroSDExpError.NO_FILE
            return 0
        if self._append_mode:
            self._last_error = MicroSDExpError.INVALID
            return 0
        chunk = bytes(data[:config.CHUNK_BYTES])
        st = self.read_status()
        if st is None:
            self._last_error = MicroSDExpError.NO_MODULE
            return 0
        if st.state == protocol.MICROSDEXP_ST_ERROR:
            self._last_error = MicroSDExpError.CARD_ERR
            return 0
        if st.rx_free < len(chunk):
            return 0  # would block
        if not self._write(bytes([protocol.MICROSDEXP_CMD_WRITE]) + chunk):
            return 0
        self._written += len(chunk)
        self._last_error = MicroSDExpError.OK
        return len(chunk)

    def read_now(self, n):
        """Drain only what is staged right now. Returns bytes (b"" = try later)."""
        if n <= 0 or not self._file_open or not self._read_started or self._async_pending:
            return b""
        st = self.read_status()
        if st is None:
            self._last_error = MicroSDExpError.NO_MODULE
            return b""
        if st.state == protocol.MICROSDEXP_ST_ERROR:
            self._last_error = MicroSDExpError.CARD_ERR
            return b""
        if st.tx_avail == 0:
            return b""
        want = min(st.tx_avail, n, self._read_chunk)
        try:
            with self._device:
                got = bytearray(want)
                self._device.write_then_readinto(
                    bytes([protocol.MICROSDEXP_CMD_READ]), got
                )
            got_bytes = bytes(got)
        except OSError:
            self._last_error = MicroSDExpError.CARD_ERR
            got_bytes = b""
        self._last_error = MicroSDExpError.OK
        return got_bytes

    def committed_bytes(self):
        """Committed byte count from one STATUS read (0 on I/O error)."""
        st = self.read_status()
        return st.result if st is not None else 0

    # ---- expansion pins + bit-bang engine ----
    def set_pin_mode(self, pin, mode):
        """Put an expansion pin in ``mode`` (0 = digital output).

        Applies immediately in RAM. Modes persist to the module EEPROM only on
        an explicit :meth:`save_pin_mode` -- the module never writes EEPROM on a
        mode change, so repeated identical applies are a library-side no-op. An
        out-of-range mode is rejected with no bus transaction.
        """
        cmd = _PIN_MODE_CMD.get(pin)
        if cmd is None:
            self._last_error = MicroSDExpError.INVALID
            return False
        # Dedup: only RAM applies, only an explicit save persists, so a
        # redundant apply writes nothing and never churns the EEPROM.
        if pin in self._pin_last_mode and self._pin_last_mode[pin] == mode:
            return True
        self._pin_last_mode[pin] = mode
        return self._write(bytes([cmd, mode & 0xFF]))

    def save_pin_mode(self):
        """Persist the configured pin modes + I2C address to module EEPROM.

        Sends CMD_SAVEEEPROM (0x1A): STOP only, no payload. Pin modes already
        took effect in RAM via :meth:`set_pin_mode`; this writes them to EEPROM
        so they survive a reset/power loss. This is the only command that
        persists -- call it once when configuration is final to avoid wearing
        the EEPROM on dev-loop churn.
        """
        return self._write(bytes([protocol.MICROSDEXP_CMD_SAVEEEPROM]))

    def write_pin(self, pin, value):
        """Drive an output-mode expansion pin high (1) or low (0)."""
        cmd = _PIN_CONTROL_CMD.get(pin)
        if cmd is None:
            self._last_error = MicroSDExpError.INVALID
            return False
        return self._write(bytes([cmd, 1 if value else 0]))

    def bitbang_set_mode(self, pin):
        """Select the bit-bang engine's data pin (PA5 / PB2 / PB3).

        This only selects the pin for the engine; it does not set its
        direction -- call :meth:`set_pin_mode` first.
        """
        if pin not in _PIN_IDS:
            self._last_error = MicroSDExpError.INVALID
            return False
        return self._write(bytes([protocol.MICROSDEXP_CMD_BITBANG_SET_MODE, pin]))

    def bitbang_buffer(self, offset, data, length=None):
        """Copy bytes into the module's 256 B workspace at ``offset``.

        Long payloads are split into ``config.BITBANG_MAX``-sized writes:
        the 3-byte header and the payload must travel in one transaction.
        A request that leaves the 256 B workspace is rejected locally with
        ``MicroSDExpError.INVALID`` instead of relying on the module to drop
        the extra bytes.
        """
        if not data:
            self._last_error = MicroSDExpError.INVALID
            return False
        buf = bytes(data)
        count = len(buf) if length is None else min(int(length), len(buf))
        if (
            count <= 0
            or offset < 0
            or offset >= protocol.BITBANG_WORKSPACE_SIZE
            or (offset + count) > protocol.BITBANG_WORKSPACE_SIZE
        ):
            self._last_error = MicroSDExpError.INVALID
            return False
        sent = 0
        while sent < count:
            chunk = count - sent
            if chunk > config.BITBANG_MAX:
                chunk = config.BITBANG_MAX
            at = offset + sent
            payload = bytes(
                [
                    protocol.MICROSDEXP_CMD_BITBANG_BUFFER,
                    at & 0xFF,
                    (at >> 8) & 0xFF,
                    chunk,
                ]
            ) + buf[sent : sent + chunk]
            if not self._write(payload):
                return False
            sent += chunk
        return True

    def bitbang_execute(self, profile):
        """Run a bit-bang profile (0x01 NeoPixel, 0x02 script).

        The module plays it from its own loop with interrupts masked, so
        it serves no I2C until the blit or script finishes.
        """
        return self._write(bytes([protocol.MICROSDEXP_CMD_BITBANG_EXECUTE, profile & 0xFF]))

    def bitbang_clear(self):
        """Zero the workspace and the module's buffered-length mark."""
        self._write(bytes([protocol.MICROSDEXP_CMD_BITBANG_CLEAR]))

    def show_neopixels(self, pin, grb, pixel_count=None):
        """Push a WS2812B frame (raw GRB triplets) and latch it.

        ``grb`` holds three bytes per pixel, green first; ``pixel_count``
        defaults to ``len(grb) // 3``. A frame holds at most 85 pixels
        (255 of the 256 B workspace).

        The pin must already be a digital output
        (``set_pin_mode(pin, 0)``), and the sketch must leave a frame time
        (~30 us/pixel plus the latch reset) before the next I2C command --
        the module clocks the frame out after it ACKs the execute.
        """
        if not grb:
            self._last_error = MicroSDExpError.INVALID
            return False
        buf = bytes(grb)
        count = len(buf) // 3 if pixel_count is None else int(pixel_count)
        if count <= 0 or count * 3 > 255:
            self._last_error = MicroSDExpError.INVALID
            return False
        if not self.bitbang_set_mode(pin):
            return False
        if not self.bitbang_buffer(0, buf[: count * 3]):
            return False
        return self.bitbang_execute(protocol.MICROSDEXP_BITBANG_PROFILE_NEOPIXEL)

    def set_clock_time(self, year, month, day, hour, minute, second):
        """Write 6 B [Y,M,D,h,m,s] via 0x0E (STOP applies)."""
        ok = self._write(
            bytes(
                [
                    protocol.MICROSDEXP_CMD_CLOCK_SET,
                    year & 0xFF,
                    month & 0xFF,
                    day & 0xFF,
                    hour & 0xFF,
                    minute & 0xFF,
                    second & 0xFF,
                ]
            )
        )
        self._last_error = MicroSDExpError.OK if ok else MicroSDExpError.NO_MODULE

    def reboot(self):
        ok = self._write(bytes([protocol.MICROSDEXP_CMD_REBOOT]))
        self._last_error = MicroSDExpError.OK if ok else MicroSDExpError.NO_MODULE

    def format(self, mode=0):
        """Explicit-only format (no token — guards live in sketch/UI)."""
        if mode > 1:
            self._last_error = MicroSDExpError.INVALID
            return False
        st = self.read_status()
        done_before = st.op_done if st is not None else 0
        if not self._write(bytes([protocol.MICROSDEXP_CMD_FORMAT, mode & 0xFF])):
            return False
        # A full FAT rebuild takes tens of seconds on a multi-GB card, so it
        # waits on its own 300 s budget instead of OP_TIMEOUT_MS.
        err = self.wait_for_op_complete(done_before, config.FORMAT_TIMEOUT_MS,
                                        scale=False)
        if err != 0:
            self._last_error = MicroSDExpError.TIMEOUT if err == -1 else MicroSDExpError.CARD_ERR
            return False
        self._last_error = MicroSDExpError.OK
        return True

    def list_dir(self, path, max_entries=64):
        """Enumerate a directory via the 0x08 TX-stream.

        Stream: 'F'/'D' + NUL basename + 4 B size LE; 0xFF terminates.
        Returns a list of DirEntry (capped at max_entries)."""
        if not self.valid_path(path) or max_entries == 0:
            return []
        st = self.read_status()
        done_before = st.op_done if st is not None else 0
        if not self._submit_filename(path):
            return []
        if not self._write(bytes([protocol.MICROSDEXP_CMD_LIST_DIR])):
            return []
        if self.wait_for_op_complete(done_before) != 0:
            self._barrier_close_flush()
            return []
        stchk = self.read_status()
        if stchk is not None and stchk.state == protocol.MICROSDEXP_ST_ERROR:
            self._barrier_close_flush()
            return []

        entries = []
        p_type, p_name, p_size = 0, 1, 2
        pstate = p_type
        is_dir = False
        sz_acc = 0
        sz_idx = 0
        name = bytearray()
        finished = False
        t0 = time.monotonic()
        limit = self.scale_timeout(config.COMMIT_TIMEOUT_MS) / 1000.0

        while not finished:
            if (time.monotonic() - t0) >= limit:
                self._last_error = MicroSDExpError.TIMEOUT
                break
            st = self.read_status()
            if st is None:
                time.sleep(self._poll_ms / 1000.0)
                continue
            if st.state == protocol.MICROSDEXP_ST_ERROR:
                self._last_error = MicroSDExpError.CARD_ERR
                entries = []
                break
            if st.tx_avail > 0:
                want = min(st.tx_avail, len(self._shared))
                n = self._write_then_read(bytes([protocol.MICROSDEXP_CMD_READ]), want, self._shared)
                for i in range(n):
                    if finished:
                        break
                    b = self._shared[i]
                    if pstate == p_type:
                        if b == protocol.LIST_END:
                            finished = True
                        elif b == 0x46 or b == 0x44:  # 'F'/'D'
                            is_dir = b == 0x44
                            name = bytearray()
                            sz_acc = 0
                            sz_idx = 0
                            pstate = p_name
                        else:
                            finished = True  # corrupt stream
                    elif pstate == p_name:
                        if b == 0x00:
                            pstate = p_size
                        else:
                            if len(name) < 63:
                                name.append(b)
                    else:  # p_size
                        sz_acc |= b << (8 * sz_idx)
                        sz_idx += 1
                        if sz_idx >= 4:
                            if len(entries) < max_entries:
                                entries.append(
                                    DirEntry(
                                        is_dir=is_dir,
                                        name=bytes(name).decode("ascii", "replace"),
                                        size=0 if is_dir else sz_acc,
                                    )
                                )
                            pstate = p_type
                continue
            if st.state == protocol.MICROSDEXP_ST_COMPLETE:
                break
            time.sleep(self._poll_ms / 1000.0)

        preserved = self._last_error
        self._barrier_close_flush()
        # Preserve a drain error across the barrier (barrier resets lastError).
        if self._last_error == MicroSDExpError.OK and preserved != MicroSDExpError.OK:
            self._last_error = preserved
        return entries

    # ---- async file core ----
    def open_append(self, path):
        """Legacy append (0x04). No module OPEN now — each write() is one
        atomic APPEND transaction (0x01 + 0x04 + payload)."""
        if not self.valid_path(path):
            return False
        self._append_path = path
        self._append_mode = True
        self._file_open = True
        self._read_started = False
        self._written = 0
        self._last_error = MicroSDExpError.OK
        self._last_active = time.monotonic()
        return True

    def _append_chunk(self, data):
        st = self.read_status()
        done_before = st.op_done if st is not None else 0
        if not self._submit_filename(self._append_path):
            return False
        if not self._write(bytes([protocol.MICROSDEXP_CMD_APPEND_FILE]) + bytes(data)):
            return False
        err = self.wait_for_op_complete(done_before)
        if err != 0:
            self._last_error = MicroSDExpError.TIMEOUT if err == -1 else MicroSDExpError.CARD_ERR
            return False
        self._last_error = MicroSDExpError.OK
        return True

    def _open_via_cmd(self, cmd, path):
        if not self.valid_path(path):
            return False
        self._append_mode = False
        try:
            raw = path.encode("ascii") + b"\x00"
        except (UnicodeEncodeError, AttributeError):
            self._last_error = MicroSDExpError.INVALID
            return False
        for _attempt in range(6):
            self._barrier_close_flush()
            st = self.read_status()
            done_before = st.op_done if st is not None else 0
            if not self._write(bytes([cmd]) + raw):
                time.sleep(0.2)
                continue
            err = self.wait_for_op_complete(done_before)
            if err == 0:
                st2 = self.read_status()
                self._base_written = st2.result if st2 is not None else 0
                self._file_open = True
                self._read_started = False
                self._written = 0
                self._last_error = MicroSDExpError.OK
                return True
            self._last_error = MicroSDExpError.TIMEOUT if err == -1 else MicroSDExpError.OPEN_FAIL
            time.sleep(0.2)
        self._file_open = False
        return False

    def open_write(self, path):
        """OPEN_WRITE (truncate). 6 attempts, first barrier unconditional."""
        return self._open_via_cmd(protocol.MICROSDEXP_CMD_OPEN_WRITE, path)

    def open_read(self, path):
        """OPEN_READ + prime the TX stream (0x23 with STOP)."""
        if not self._open_via_cmd(protocol.MICROSDEXP_CMD_OPEN_READ, path):
            return False
        # Prime the read stream (C++ openRead does this STOP).
        if not self._write(bytes([protocol.MICROSDEXP_CMD_READ])):
            self._last_error = MicroSDExpError.NO_FILE
        self._read_started = True
        st = self.read_status()
        if st is not None:
            self._base_written = st.result
        self._last_error = MicroSDExpError.OK
        return True

    def write(self, data):
        """Flow-paced push. Returns bytes accepted."""
        if not data or not self._file_open:
            if not self._file_open:
                self._last_error = MicroSDExpError.NO_FILE
            return 0
        if self._append_mode:
            off = 0
            buf = bytes(data)
            while off < len(buf):
                chunk = buf[off : off + config.CHUNK_BYTES]
                if not self._append_chunk(chunk):
                    self._written += off
                    return off
                off += len(chunk)
            self._written += off
            self._last_error = MicroSDExpError.OK
            return off
        buf = bytes(data)
        off = 0
        while off < len(buf):
            chunk = buf[off : off + config.CHUNK_BYTES]
            if not self._push_write_block(bytearray(chunk)):
                self._written += off
                return off
            off += len(chunk)
        self._written += off
        self._last_error = MicroSDExpError.OK
        return off

    def _push_write_block(self, chunk):
        max_attempts = 1200 if 0 < self._scl_hz < 50000 else 400
        for _attempt in range(max_attempts):
            st = self.read_status()
            if st is None:
                time.sleep(self._flow_poll_ms / 1000.0)
                continue
            if st.state == protocol.MICROSDEXP_ST_ERROR:
                self._last_error = MicroSDExpError.CARD_ERR
                return False
            if st.rx_free < len(chunk):
                time.sleep(self._flow_poll_ms / 1000.0)
                continue
            if self._write(bytes([protocol.MICROSDEXP_CMD_WRITE]) + bytes(chunk)):
                return True
            time.sleep(0.001)
        self._last_error = MicroSDExpError.TIMEOUT
        return False

    def read(self, n):
        """Read up to n bytes. Returns bytes (short at EOF)."""
        if n == 0 or not self._file_open:
            if not self._file_open:
                self._last_error = MicroSDExpError.NO_FILE
            return b""
        if self._append_mode:
            self._last_error = MicroSDExpError.INVALID
            return b""
        out = bytearray()
        t0 = time.monotonic()
        limit = self.scale_timeout(config.COMMIT_TIMEOUT_MS) / 1000.0
        while len(out) < n:
            if (time.monotonic() - t0) >= limit:
                self._last_error = MicroSDExpError.TIMEOUT
                break
            st = self.read_status()
            if st is None:
                time.sleep(self._poll_ms / 1000.0)
                continue
            if st.state == protocol.MICROSDEXP_ST_ERROR:
                self._last_error = MicroSDExpError.CARD_ERR
                break
            if st.tx_avail > 0:
                want = min(st.tx_avail, n - len(out), self._read_chunk)
                try:
                    with self._device:
                        got = bytearray(want)
                        self._device.write_then_readinto(
                            bytes([protocol.MICROSDEXP_CMD_READ]), got
                        )
                    out.extend(got)
                    self._last_active = time.monotonic()
                    continue
                except OSError:
                    if want > 128:
                        # This port caps one bus transaction below the
                        # configured chunk (nRF TWIM is 255 B). Drop to the
                        # always-safe 128 B and retry the drain.
                        self._read_chunk = 128
                        continue
                    self._last_error = MicroSDExpError.CARD_ERR
                    break
            if st.state == protocol.MICROSDEXP_ST_COMPLETE:
                break
            time.sleep(self._poll_ms / 1000.0)
        else:
            pass
        self._last_error = MicroSDExpError.OK if len(out) > 0 else self._last_error
        if len(out) == n:
            self._last_error = MicroSDExpError.OK
        self._written = len(out)
        return bytes(out)

    def sync(self):
        if not self._file_open or self._append_mode or self._read_started:
            return True
        target = self._base_written + self._written
        ok = self.wait_for_committed(target)
        self._last_error = MicroSDExpError.OK if ok else MicroSDExpError.TIMEOUT
        return ok

    def close(self):
        if not self._file_open:
            return True
        if self._append_mode:
            self._file_open = False
            self._append_mode = False
            self._read_started = False
            self._last_error = MicroSDExpError.OK
            return True
        ok = self.sync()
        st = self.read_status()
        db = st.op_done if st is not None else 0
        if not self._write(bytes([protocol.MICROSDEXP_CMD_CLOSE_FLUSH])):
            self._last_error = MicroSDExpError.CARD_ERR
            self._file_open = False
            self._read_started = False
            return False
        cw = self.wait_for_op_complete(db)
        self._file_open = False
        self._read_started = False
        if cw != 0:
            self._last_error = MicroSDExpError.TIMEOUT if cw == -1 else MicroSDExpError.CARD_ERR
            return False
        self._last_error = MicroSDExpError.OK
        return ok

    # ---- File-style helpers (mirror C++ openFile) ----
    def open(self, path, mode="r"):
        """``open(path, "r"|"w"|"a")`` -> MicroSDExpFile or None.

        Mode is the first char (``r`` read, ``w`` write/truncate, ``a``
        append via legacy 0x04). Mirrors the C++ ``openFile()``."""
        m = (mode or "")[:1].lower()
        if m == "w":
            ok = self.open_write(path)
        elif m == "a":
            ok = self.open_append(path)
        elif m == "r":
            ok = self.open_read(path)
        else:
            return None
        if not ok:
            return None
        return MicroSDExpFile(self, mode_code={"r": 0, "w": 1, "a": 2}.get(m, 0))


class MicroSDExpFile:
    """Single-file handle (module is single-file). Context-manager ready."""

    def __init__(self, microSDexp, mode_code=0):
        self._microSDexp = microSDexp
        self._open = True
        self.mode = mode_code  # 0=r, 1=w, 2=a
        self.nil = False

    @property
    def microSDexp(self):
        return self._microSDexp

    @property
    def is_open(self):
        return self._open

    def write(self, data):
        if not self._open or self._microSDexp is None:
            return 0
        n = self._microSDexp.write(bytes(data))
        return n

    def read(self, n):
        if not self._open or self._microSDexp is None:
            return b""
        return self._microSDexp.read(n)

    def sync(self):
        if not self._open or self._microSDexp is None:
            return False
        return self._microSDexp.sync()

    def close(self):
        if not self._open or self._microSDexp is None:
            return False
        ok = self._microSDexp.close()
        self._open = False
        return ok

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self._open:
            self.close()
        return False


def open_file(microSDexp, path, mode="r"):
    """Module helper mirroring C++ ``openFile(&microSDexp, path, "r"|"w"|"a")``."""
    return microSDexp.open(path, mode)





