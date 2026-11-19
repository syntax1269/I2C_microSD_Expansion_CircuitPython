# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""mock_module — desktop in-memory module for tests (no hardware).

Implements the subset of ``I2CDevice`` the library uses:

* ``device_address`` (mutable for the begin() scan),
* ``write(payload)`` — STOP transactions (0x01/0x21/0x22/0x24/0x25/0x28/0x2F/legacy),
* ``write_then_readinto(out, inn)`` — repeated-START reads (STATUS 0x20,
  VERSION 0x0F, READ 0x23, CARD_INFO 0x29, TEMP 0x17, ADC 0x18),
* ``__enter__/__exit__`` (lock no-op).

State machine mirrors the real module closely enough for the suite:

* files are ``dict[path, bytearray]`` (paths normalized Casefold + strip
  leading slash, trailing slash treated as dir in legacy ops),
* ``op_done`` advances on every STOP op; STATUS latches ``result``,
* WRITE appends to the open write file and ``result`` reports committed
  bytes after CLOSE (sync polls ``result >= base+written``),
* READ stages the file content into the TX buffer; txAvail = remaining,
* LIST_DIR streams 'F'/'D'+NUL+size LE, 0xFF terminated,
* append (0x04) appends without opening a module file (open+close per chunk).
"""

from i2c_microsd_module import protocol


class MockI2CDevice:
    def __init__(self, address=0x6E):
        self.device_address = address
        self._files = {}
        self._dirs = {"/"}
        self._filename = ""
        self._open_path = None
        self._open_mode = None  # "w" r/w, "r"
        self._write_pos = 0
        self._read_pos = 0
        self._op_done = 0
        self._state = protocol.MICROSDEXP_ST_IDLE
        self._pending_result = 0
        self._committed = 0
        self._version = b"18.7.6"
        self._short_read = 0  # bytes to truncate the next read by (0=off)
        self._pa5_mode = 0
        self._pb2_mode = 0
        self._pb3_mode = 0
        # EEPROM: only set once an explicit save command has been received.
        self._eeprom_saved = False
        # Bit-bang engine state (256 B workspace, buffered-length mark).
        self._bb_pin = 0
        self._bb_ws = bytearray(protocol.BITBANG_WORKSPACE_SIZE)
        self._bb_len = 0
        self._bb_profile = 0

    # ---- lock ----
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    # ---- helpers ----
    def _norm(self, path):
        p = path.strip()
        if p.startswith("/"):
            p = p[1:]
        return p

    def _bump(self, result=None):
        self._op_done = (self._op_done + 1) & 0xFF
        if result is not None:
            self._pending_result = result
            self._committed = result

    def _status_bytes(self):
        tx_avail = 0
        if self._open_mode in ("r", "readfile") and self._open_path is not None:
            data = self._files.get(self._open_path, bytearray())
            rem = len(data) - self._read_pos
            tx_avail = min(128, max(0, rem))  # module TX buffer, 16-bit field
        if self._open_mode == "list":
            rem = len(getattr(self, "_list_payload", b"")) - getattr(self, "_list_pos", 0)
            tx_avail = min(128, max(0, rem))
        rx_free = 128 if self._open_mode == "w" else 0
        if self._open_mode == "w":
            rx_free = 128
        st = self._state
        err = protocol.MICROSDEXP_ERR_NONE
        out = bytearray(12)
        out[0] = 2  # rev
        out[1] = st
        out[2] = self._op_done
        out[3] = err
        out[4] = rx_free & 0xFF
        out[5] = (rx_free >> 8) & 0xFF
        out[6] = tx_avail & 0xFF
        out[7] = (tx_avail >> 8) & 0xFF
        r = self._pending_result
        out[8] = r & 0xFF
        out[9] = (r >> 8) & 0xFF
        out[10] = (r >> 16) & 0xFF
        out[11] = (r >> 24) & 0xFF
        return bytes(out)

    def _seed_file(self, path, data):
        self._files[self._norm(path)] = bytearray(data)

    # ---- writes (STOP) ----
    def write(self, payload, start=0, end=None):
        if end is None:
            end = len(payload)
        if not payload:
            raise OSError(2, "NACK")  # empty probe -> probe retry
        cmd = payload[start]
        data = bytes(payload[start + 1 : end])

        if cmd == protocol.MICROSDEXP_CMD_FILENAME:
            if len(data) > 259:
                raise OSError(3, "NACK filename overflow")
            self._filename = data.split(b"\x00")[0].decode("ascii", "replace")
            return
        # Pin / extension mode commands (NACK on out-of-range mode).
        if cmd == protocol.MICROSDEXP_CMD_PA5_SET_MODE:
            if data and data[0] > 4:
                raise OSError(3, "NACK mode")
            self._pa5_mode = data[0] if data else 0
            return
        if cmd == protocol.MICROSDEXP_CMD_PB2_SET_MODE:
            if data and data[0] > 3:
                raise OSError(3, "NACK mode")
            self._pb2_mode = data[0] if data else 0
            return
        if cmd == protocol.MICROSDEXP_CMD_PB3_SET_MODE:
            if data and data[0] > 3:
                raise OSError(3, "NACK mode")
            self._pb3_mode = data[0] if data else 0
            return
        if cmd in (protocol.MICROSDEXP_CMD_PA5_CONTROL, protocol.MICROSDEXP_CMD_PB2_CONTROL, protocol.MICROSDEXP_CMD_PB3_CONTROL):
            mode = {protocol.MICROSDEXP_CMD_PA5_CONTROL: getattr(self, "_pa5_mode", 0),
                    protocol.MICROSDEXP_CMD_PB2_CONTROL: getattr(self, "_pb2_mode", 0),
                    protocol.MICROSDEXP_CMD_PB3_CONTROL: getattr(self, "_pb3_mode", 0)}[cmd]
            if mode >= 2:
                raise OSError(3, "NACK control in input mode")
            return
        if cmd == protocol.MICROSDEXP_CMD_I2C_SET_ADDR:
            if not data or data[0] not in (0x6A, 0x6B, 0x6C, 0x6D, 0x6E, 0x6F):
                raise OSError(3, "NACK addr")
            self.device_address = data[0]
            return
        if cmd == protocol.MICROSDEXP_CMD_SAVEEEPROM:
            # STOP-only: latch that the current config has been committed.
            self._eeprom_saved = True
            return
        if cmd == protocol.MICROSDEXP_CMD_OPEN_WRITE:
            path = data.split(b"\x00")[0].decode("ascii", "replace")
            self._files[self._norm(path)] = bytearray()
            self._open_path = self._norm(path)
            self._open_mode = "w"
            self._write_pos = 0
            self._state = protocol.MICROSDEXP_ST_BUSY_SD
            self._bump(0)
            return
        if cmd == protocol.MICROSDEXP_CMD_OPEN_READ:
            path = data.split(b"\x00")[0].decode("ascii", "replace")
            n = self._norm(path)
            if n not in self._files:
                self._state = protocol.MICROSDEXP_ST_ERROR
                self._bump(0)
                return
            self._open_path = n
            self._open_mode = "r"
            self._read_pos = 0
            self._state = protocol.MICROSDEXP_ST_TX_READY
            self._bump(0)
            return
        if cmd == protocol.MICROSDEXP_CMD_WRITE:
            if self._open_mode != "w" or self._open_path is None:
                raise OSError(3, "NACK data")
            f = self._files[self._open_path]
            if len(data) > 128:
                raise OSError(3, "NACK data")
            f.extend(data)
            self._write_pos += len(data)
            # module commits bytes as the worker drains; surface progress
            # via STATUS.result so sync() (waitForCommitted) can complete.
            self._pending_result = len(f)
            self._committed = self._pending_result
            return
        if cmd == protocol.MICROSDEXP_CMD_READ:
            # STOP variant used to prime the read (no payload)
            return
        if cmd == protocol.MICROSDEXP_CMD_CLOSE_FLUSH:
            if self._open_mode == "w" and self._open_path is not None:
                self._pending_result = len(self._files[self._open_path])
                self._committed = self._pending_result
            self._open_path = None
            self._open_mode = None
            self._state = protocol.MICROSDEXP_ST_IDLE
            self._bump(self._pending_result)
            return
        if cmd == protocol.MICROSDEXP_CMD_APPEND_FILE:
            p = self._norm(self._filename)
            self._files.setdefault(p, bytearray())
            self._files[p].extend(data)
            self._pending_result = len(self._files[p])
            self._bump(self._pending_result)
            return
        if cmd in (
            protocol.MICROSDEXP_CMD_FILE_SIZE,
            protocol.MICROSDEXP_CMD_FILE_EXISTS,
            protocol.MICROSDEXP_CMD_IS_DIRECTORY,
            protocol.MICROSDEXP_CMD_LIST_DIR,
            protocol.MICROSDEXP_CMD_MAKE_DIR,
            protocol.MICROSDEXP_CMD_REMOVE_DIR,
            protocol.MICROSDEXP_CMD_REMOVE_FILE,
        ):
            p = self._norm(self._filename)
            if cmd == protocol.MICROSDEXP_CMD_FILE_SIZE:
                self._bump(len(self._files.get(p, bytearray())))
            elif cmd == protocol.MICROSDEXP_CMD_IS_DIRECTORY:
                self._bump(1 if (p == "" or ("/" + p) in self._dirs) else 0)
                self._state = protocol.MICROSDEXP_ST_IDLE
            elif cmd == protocol.MICROSDEXP_CMD_FILE_EXISTS:
                self._bump(1 if p in self._files or ("/" + p) in self._dirs else 0)
                if p not in self._files and self._filename != "/":
                    # keep result sticky, state idle
                    self._state = protocol.MICROSDEXP_ST_IDLE
            elif cmd == protocol.MICROSDEXP_CMD_MAKE_DIR:
                if p and p not in self._files:
                    self._dirs.add("/" + p)
                self._bump(0)
            elif cmd == protocol.MICROSDEXP_CMD_REMOVE_FILE:
                self._files.pop(p, None)
                self._bump(0)
            elif cmd == protocol.MICROSDEXP_CMD_REMOVE_DIR:
                self._dirs.discard("/" + p)
                self._bump(0)
            elif cmd == protocol.MICROSDEXP_CMD_LIST_DIR:
                self._list_payload = self._build_list()
                self._list_pos = 0
                self._open_mode = "list"
                self._open_path = p
                self._bump(0)
            return
        if cmd == protocol.MICROSDEXP_CMD_WRITE_FILE:
            p = self._norm(self._filename)
            self._files[p] = bytearray(data)
            self._pending_result = len(data)
            self._bump(len(data))
            return
        if cmd == protocol.MICROSDEXP_CMD_APPEND_FILE:
            p = self._norm(self._filename)
            self._files.setdefault(p, bytearray())
            self._files[p].extend(data)
            self._pending_result = len(self._files[p])
            self._bump(self._pending_result)
            return
        if cmd == protocol.MICROSDEXP_CMD_READ_FILE:
            p = self._norm(self._filename)
            if p not in self._files:
                self._state = protocol.MICROSDEXP_ST_ERROR
                self._bump(0)
                return
            self._open_path = p
            self._open_mode = "readfile"
            self._read_pos = 0
            self._state = protocol.MICROSDEXP_ST_TX_READY
            self._bump(0)
            return
        if cmd == protocol.MICROSDEXP_CMD_FORMAT:
            if data and data[0] > 1:
                raise OSError(3, "NACK format mode")
            self._files = {}
            self._bump(0)
            return
        if cmd == protocol.MICROSDEXP_CMD_CLOCK_SET:
            if len(data) != 6:
                raise OSError(3, "NACK clock len")
            self._bump(0)
            return
        if cmd == protocol.MICROSDEXP_CMD_REBOOT:
            self._bump(0)
            return
        if cmd in (protocol.MICROSDEXP_CMD_BITBANG_CLEAR, protocol.MICROSDEXP_CMD_BITBANG_SET_MODE,
                   protocol.MICROSDEXP_CMD_BITBANG_BUFFER, protocol.MICROSDEXP_CMD_BITBANG_EXECUTE):
            if cmd == protocol.MICROSDEXP_CMD_BITBANG_SET_MODE:
                if not data or data[0] not in (2, 3, 5):
                    raise OSError(3, "NACK bitbang pin")
                self._bb_pin = data[0]
                return
            if cmd == protocol.MICROSDEXP_CMD_BITBANG_BUFFER:
                # [offLSB, offMSB, len, ...] — require exact shape
                if len(data) < 3 or len(data) != 3 + data[2]:
                    raise OSError(3, "NACK bitbang buffer")
                off = data[0] | (data[1] << 8)
                for i in range(data[2]):
                    if off + i < protocol.BITBANG_WORKSPACE_SIZE:
                        self._bb_ws[off + i] = data[3 + i]
                end = min(protocol.BITBANG_WORKSPACE_SIZE, off + data[2])
                if end > self._bb_len:
                    self._bb_len = end
                return
            if cmd == protocol.MICROSDEXP_CMD_BITBANG_EXECUTE:
                if not data:
                    raise OSError(3, "NACK bitbang profile")
                self._bb_profile = data[0]
                return
            # CLEAR: zero the workspace, drop the buffered-length mark
            self._bb_ws = bytearray(protocol.BITBANG_WORKSPACE_SIZE)
            self._bb_len = 0
            return
        raise OSError(3, "unknown cmd 0x%02x" % cmd)

    def _build_list(self):
        out = bytearray()
        names = sorted(self._files.values(), key=lambda b: bytes(b).hex())
        # Re-emit per file name (stable order)
        for name in sorted(self._files):
            out.append(0x46)  # 'F'
            out.extend(name.encode("ascii"))
            out.append(0x00)
            sz = len(self._files[name])
            out.extend(bytes([sz & 0xFF, (sz >> 8) & 0xFF, (sz >> 16) & 0xFF, (sz >> 24) & 0xFF]))
        out.append(protocol.LIST_END)
        return bytes(out)

    # ---- reads (repeated START) ----
    def write_then_readinto(self, out_buffer, in_buffer, out_start=0, out_end=None, in_start=0, in_end=None):
        if out_end is None:
            out_end = len(out_buffer)
        if in_end is None:
            in_end = len(in_buffer)
        cmd = out_buffer[out_start] if out_end - out_start >= 1 else None
        want = in_end - in_start

        if cmd == protocol.MICROSDEXP_CMD_STATUS:
            data = self._status_bytes()
        elif cmd == protocol.MICROSDEXP_CMD_VERSION:
            data = self._version
        elif cmd == protocol.MICROSDEXP_CMD_TEMP_READ:
            data = bytes([0x10, 0x01])  # 0x0110 = 272 raw
        elif cmd == protocol.MICROSDEXP_CMD_ADC_READ_PA5:
            data = bytes([0x34, 0x12, 0x00])
        elif cmd == protocol.MICROSDEXP_CMD_ADC_READ_PB3:
            data = b"\xff"
        elif cmd == protocol.MICROSDEXP_CMD_PIN_STATE_READ:
            data = b"\x00"
        elif cmd == protocol.MICROSDEXP_CMD_DIAG:
            data = bytes(16)  # shipping zeros are accepted
        elif cmd == protocol.MICROSDEXP_CMD_DIAG2:
            data = bytes(16)
        elif cmd == protocol.MICROSDEXP_CMD_SD_DIAG:
            data = bytes(16)
        elif cmd == protocol.MICROSDEXP_CMD_CARD_INFO:
            data = bytes(
                [
                    1,  # mounted
                    3,  # fat32
                    2,  # sdhc
                    0,
                ]
            ) + (8388608).to_bytes(4, "little") + (1048576).to_bytes(4, "little") + (4096).to_bytes(2, "little") + (0).to_bytes(2, "little") + (2097152).to_bytes(4, "little") + (5000000).to_bytes(4, "little")
        elif cmd == protocol.MICROSDEXP_CMD_READ:
            if self._open_mode == "list":
                data = self._list_payload[self._list_pos : self._list_pos + want]
                self._list_pos += len(data)
                if self._list_pos >= len(self._list_payload):
                    self._open_mode = None
            elif self._open_mode in ("r", "readfile") and self._open_path is not None:
                f = self._files[self._open_path]
                remaining = len(f) - self._read_pos
                take = min(want, remaining)
                if self._short_read:
                    take = max(0, take - self._short_read)
                    self._short_read = 0
                data = bytes(f[self._read_pos : self._read_pos + take])
                self._read_pos += len(data)
                if self._read_pos >= len(f):
                    self._state = protocol.MICROSDEXP_ST_COMPLETE
            else:
                data = b""
        else:
            raise OSError(3, "unknown read cmd 0x%02x" % (cmd or 0))

        n = min(len(data), want)
        in_buffer[in_start : in_start + n] = data[:n]
        in_buffer[in_start + n : in_end] = bytes(in_end - in_start - n)




