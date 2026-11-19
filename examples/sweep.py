# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""Full performance sweep (I²C microSD Expansion).

Runs 64 KB CRC round-trip at 100 kHz / 400 kHz / 1 MHz plus
legacy battery. Pattern b[i] = (i*7+3)&0xFF, CRC32 must be D660AF09.
"""

import binascii
import gc
import time

import board
import busio

from i2c_microsd_module import I2CmicroSD

KBYTES = 65536
SPEEDS = (100000, 400000, 1000000)


def roundtrip(microSDexp, hz, path):
    microSDexp._scl_hz = hz  # timeout scaling must match bus freq
    t0 = time.monotonic()
    w = microSDexp.open(path, "w")
    if w is None:
        print(f"RESULT hz={hz} open_w FAIL err={microSDexp.last_error}")
        return
    # Prebuilt tile per 64B (pattern is periodic in 256B, tile per offset)
    tiles = {}
    for off in range(0, KBYTES, 64):
        tiles[off] = bytes((((off + i) * 7 + 3) & 0xFF) for i in range(64))
    for off in range(0, KBYTES, 64):
        if w.write(tiles[off]) != 64:
            print(f"RESULT hz={hz} write_short off={off} err={microSDexp.last_error}")
            return
    if not w.close():
        print(f"RESULT hz={hz} close_w FAIL err={microSDexp.last_error}")
        return
    wms = int((time.monotonic() - t0) * 1000)

    r = microSDexp.open(path, "r")
    if r is None:
        print(f"RESULT hz={hz} open_r FAIL err={microSDexp.last_error}")
        return
    crc = 0
    got = 0
    mism = 0
    # Expected stream (same pattern, built once)
    expect = bytes((((i) * 7 + 3) & 0xFF) for i in range(KBYTES))
    t1 = time.monotonic()
    while got < KBYTES:
        # v18.8.21: two staged 128 B TX buffers -> ask 256 per call.
        data = r.read(min(256, KBYTES - got))
        if not data:
            break
        crc = binascii.crc32(data, crc)
        if data != expect[got : got + len(data)]:
            mism += 1
        got += len(data)
    r.close()
    rms = int((time.monotonic() - t1) * 1000)
    hashv = crc & 0xFFFFFFFF
    ok = got == KBYTES and mism == 0 and hashv == 0xD660AF09
    wk = KBYTES / (wms / 1000.0) / 1024 if wms else 0
    rk = KBYTES / (rms / 1000.0) / 1024 if rms else 0
    print(
        f"RESULT hz={hz} Wms={wms} Rms={rms} WkB={wk:.1f} RkB={rk:.1f} "
        f"got={got} mism={mism} hash={hashv:08X} {'PASS' if ok else 'FAIL'}"
    )


i2c = busio.I2C(board.IO1, board.IO2, frequency=400000)
microSDexp = I2CmicroSD(i2c, scl_hz=400000, poll_ms=2, flow_poll_ms=1)
print("=== Sweep S3 ===")
if not microSDexp.begin():
    print("begin FAILED")
    raise SystemExit
st = microSDexp.read_status()
print(f"STATUS rev={st.rev} state={st.state}")
print(f"version={microSDexp.version()!r}")
ci = microSDexp.card_info()
if ci is not None:
    print(f"card mounted={ci.mounted} fat={ci.fat_type} sectors={ci.sector_count} free_clusters={ci.free_clusters}")

print("legacy battery ...")
ok = True
ok &= microSDexp.mkdir("CPTEST")
print(f"mkdir CPTEST -> {ok}")
print(f"isDir CPTEST -> {microSDexp.is_directory('CPTEST')}")
print(f"exists CPTEST -> {microSDexp.exists('CPTEST')}")
w = microSDexp.open("CPTEST/LEG.BIN", "w")
if w is not None:
    w.write(b"HELLO-WORLD")
    w.close()
f = microSDexp.open("CPTEST/LEG.BIN", "a")
if f is not None:
    f.write(b"!")
    f.close()
print(f"size LEG.BIN = {microSDexp.file_size('CPTEST/LEG.BIN')} (expect 12)")
print(f"exists LEG.BIN = {microSDexp.exists('CPTEST/LEG.BIN')}")
entries = microSDexp.list_dir("CPTEST")
print(f"list CPTEST = {len(entries)} entries")
for e in entries:
    print(f"  {'D' if e.is_dir else 'F'} {e.name!r} {e.size}")
microSDexp.remove("CPTEST/LEG.BIN")
microSDexp.rmdir("CPTEST")
print(f"cleanup mkdir/rmdir -> {microSDexp.last_error}")

for hz in SPEEDS:
    i2c.deinit()
    time.sleep(0.2)
    i2c = busio.I2C(board.IO1, board.IO2, frequency=hz)
    microSDexp = I2CmicroSD(i2c, scl_hz=hz, poll_ms=2, flow_poll_ms=1)
    if not microSDexp.begin():
        print(f"RESULT hz={hz} begin FAIL")
        continue
    gc.collect()
    roundtrip(microSDexp, hz, "SWEEP64.BIN")
    time.sleep(0.5)

print("=== Sweep S3 done ===")




