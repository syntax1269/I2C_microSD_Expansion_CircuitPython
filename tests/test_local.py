# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""Desktop tests (no hardware). Run: python tests/test_local.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mock_module import MockI2CDevice
from i2c_microsd_module import I2CmicroSD, MicroSDExpError, protocol


def crc_update(crc, data):
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (0xEDB88320 ^ (crc >> 1)) if (crc & 1) else (crc >> 1)
    return crc


def make_microSDexp():
    return I2CmicroSD(MockI2CDevice(), scl_hz=400000)


def test_begin():
    b = make_microSDexp()
    assert b.begin(), f"begin failed, last_error={b.last_error}"
    st = b.read_status()
    assert st.rev == 2
    assert b.version() == "18.7.6"
    info = b.card_info()
    assert info.mounted == 1
    assert info.sector_count == 8388608
    print("test_begin PASS")


def test_roundtrip_64k():
    b = make_microSDexp()
    assert b.begin()
    w = b.open("Example64K.BIN", "w")
    assert w is not None
    chunk = bytearray(64)
    for off in range(0, 65536, 64):
        for i in range(64):
            chunk[i] = ((off + i) * 7 + 3) & 0xFF
        assert w.write(chunk) == 64
    assert w.close()
    r = b.open("Example64K.BIN", "r")
    assert r is not None
    crc = 0xFFFFFFFF
    got = 0
    mism = 0
    while got < 65536:
        data = r.read(min(128, 65536 - got))
        if not data:
            break
        for i, byte in enumerate(data):
            if byte != (((got + i) * 7 + 3) & 0xFF):
                mism += 1
        crc = crc_update(crc, data)
        got += len(data)
    r.close()
    hashv = crc ^ 0xFFFFFFFF
    assert got == 65536 and mism == 0 and hashv == 0xD660AF09, (
        f"got={got} mism={mism} hash={hashv:08X}"
    )
    print("test_roundtrip_64k PASS (D660AF09)")


def test_append_and_queries():
    b = make_microSDexp()
    assert b.begin()
    w = b.open("NANO.TXT", "w")
    assert w is not None
    w.write(b"HELLO-WORLD")
    w.close()
    a = b.open("NANO.TXT", "a")
    assert a is not None
    a.write(b"!")
    a.close()
    assert b.file_size("NANO.TXT") == 12, b.file_size("NANO.TXT")
    assert b.exists("NANO.TXT")
    assert b.is_directory("/")
    entries = b.list_dir("/")
    assert any(e.name == "NANO.TXT" for e in entries), entries
    print("test_append_and_queries PASS")


def test_pins_and_bitbang():
    dev = MockI2CDevice()
    b = I2CmicroSD(dev, scl_hz=400000)
    assert b.begin()

    # Pin control: mode 0 = digital output, then a level write.
    assert b.set_pin_mode(protocol.MICROSDEXP_PIN_PB2, 0)
    assert b.write_pin(protocol.MICROSDEXP_PIN_PB2, 1)
    assert dev._pb2_mode == 0
    assert not b.set_pin_mode(99, 0) and b.last_error == MicroSDExpError.INVALID

    # NeoPixel frame: 4 px, one GRB triplet per pixel.
    frame = bytes([0, 40, 0] * 4)
    assert b.show_neopixels(protocol.MICROSDEXP_PIN_PA5, frame)
    assert dev._bb_pin == protocol.MICROSDEXP_PIN_PA5
    assert dev._bb_profile == protocol.MICROSDEXP_BITBANG_PROFILE_NEOPIXEL
    assert bytes(dev._bb_ws[:12]) == frame and dev._bb_len == 12

    # 85 px = 255 B is the frame limit and splits into 120/120/15 writes.
    big = bytes((i * 5 + 1) & 0xFF for i in range(85 * 3))
    assert b.show_neopixels(protocol.MICROSDEXP_PIN_PB3, big)
    assert bytes(dev._bb_ws[: len(big)]) == big and dev._bb_len == 255

    # 86 px would need 258 B: rejected before any bus traffic.
    assert not b.show_neopixels(protocol.MICROSDEXP_PIN_PA5, bytes(86 * 3))
    assert b.last_error == MicroSDExpError.INVALID

    # Script profile: SET_HIGH, DELAY_MS 200, SET_LOW, DELAY_MS 200, LOOP 5.
    script = bytes([0x01, 0x04, 200, 0x02, 0x04, 200, 0x05, 0x00, 5])
    b.bitbang_clear()
    assert dev._bb_len == 0
    assert b.bitbang_buffer(0, script)
    assert b.bitbang_execute(protocol.MICROSDEXP_BITBANG_PROFILE_SCRIPT)
    assert bytes(dev._bb_ws[: len(script)]) == script
    assert dev._bb_profile == protocol.MICROSDEXP_BITBANG_PROFILE_SCRIPT

    assert not b.bitbang_set_mode(7) and b.last_error == MicroSDExpError.INVALID
    print("test_pins_and_bitbang PASS")


def test_save_pin_mode_on_command_only():
    b = I2CmicroSD(MockI2CDevice(), scl_hz=400000)
    assert b.begin()
    dev = b._device
    assert dev._eeprom_saved is False
    # save before anything else is a no-op on state, still no auto-persist:
    assert b.set_pin_mode(protocol.MICROSDEXP_PIN_PB2, 0)
    assert dev._eeprom_saved is False  # setting a mode never writes EEPROM
    assert b.save_pin_mode()             # explicit -> save is recorded
    assert dev._eeprom_saved is True
    # idempotent: saving again after more churn is still just the command.
    assert b.set_pin_mode(protocol.MICROSDEXP_PIN_PB3, 1)
    assert b.save_pin_mode()
    assert dev._eeprom_saved is True
    print("test_save_pin_mode_on_command_only PASS")


def test_timeout_scaling():
    b = I2CmicroSD(MockI2CDevice(), scl_hz=100000)
    assert b.scale_timeout(15000) == 15000
    b_low = I2CmicroSD(MockI2CDevice(), scl_hz=25000)
    assert b_low.scale_timeout(15000) == 60000  # 15s * 100k/25k = 60s (also >=2x)
    b_fast = I2CmicroSD(MockI2CDevice(), scl_hz=1000000)
    assert b_fast.scale_timeout(15000) == 15000
    print("test_timeout_scaling PASS")


def test_read_eof():
    b = make_microSDexp()
    assert b.begin()
    w = b.open("small.bin", "w")
    w.write(b"abc")
    w.close()
    r = b.open("small.bin", "r")
    data = r.read(10)
    assert data == b"abc", data
    r.close()
    print("test_read_eof PASS")



def test_bitbang_workspace_bounds():
    b = I2CmicroSD(MockI2CDevice(), scl_hz=400000)
    assert b.begin()
    # The whole 256 B workspace is addressable.
    assert b.bitbang_buffer(0, bytes(protocol.BITBANG_WORKSPACE_SIZE))
    before = b._device._bb_len
    # Anything leaving it must fail locally, with no bus traffic.
    for offset, count in ((200, 100), (256, 1), (0xFFFF, 1), (-1, 1)):
        assert not b.bitbang_buffer(offset, bytes(count))
        assert b.last_error == MicroSDExpError.INVALID
        assert b._device._bb_len == before
    print("test_bitbang_workspace_bounds PASS")


def test_sticky_error():
    b = I2CmicroSD(MockI2CDevice(), scl_hz=400000)
    assert b.begin()
    assert b.sticky_error == MicroSDExpError.OK
    assert not b.bitbang_set_mode(7)          # INVALID, no bus traffic
    assert b.last_error == MicroSDExpError.INVALID
    assert b.version()                        # a later, successful call
    assert b.last_error == MicroSDExpError.OK
    assert b.sticky_error == MicroSDExpError.INVALID
    b.clear_error()
    assert b.sticky_error == MicroSDExpError.OK
    assert b.last_error == MicroSDExpError.OK
    print("test_sticky_error PASS")


if __name__ == "__main__":
    test_begin()
    test_roundtrip_64k()
    test_append_and_queries()
    test_pins_and_bitbang()
    test_save_pin_mode_on_command_only()
    test_timeout_scaling()
    test_read_eof()
    test_bitbang_workspace_bounds()
    test_sticky_error()
    print("ALL PASS")




