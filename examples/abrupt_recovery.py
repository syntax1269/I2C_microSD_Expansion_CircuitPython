# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""Abrupt-recovery test: 7 s I2C silence recovery for the I²C microSD Expansion.

Phase 1: OPEN_WRITE + partial 2048 B write -> 7 s silence.
Phase 2: STATUS/CARD_INFO alive, file == 2048 B prefix byte-perfect.
Phase 3: OPEN_READ + partial drain -> 7 s silence -> full re-read.
Phase 4: fresh 1 KB round-trip.
"""

import binascii
import time

import board
import busio

from i2c_microsd_module import I2CmicroSD

HZ = 400000
fails = 0


def check(ok, what):
    global fails
    print(f"  {what}: {'OK' if ok else 'FAIL'}")
    if not ok:
        fails += 1


i2c = busio.I2C(board.IO1, board.IO2, frequency=HZ)
b = I2CmicroSD(i2c, scl_hz=HZ, poll_ms=2, flow_poll_ms=1)
print("=== ABRUPT-STOP recovery (7 s silence x2) ===")
if not b.begin():
    print("begin FAILED")
    raise SystemExit
st = b.read_status()
check(st is not None and st.rev == 2, "STATUS alive before")

FILE = "Abrupt_S3.BIN"
PLAN = 8192
SENT = 2048
w = b.open(FILE, "w")
check(w is not None, "OPEN_WRITE before abort")
expect = bytes((((i) * 7 + 3) & 0xFF) for i in range(PLAN))
if w is not None:
    ok = True
    for o in range(0, SENT, 64):
        if w.write(expect[o:o+64]) != 64:
            ok = False
            break
    check(ok, "PARTIAL WRITE 2048 B")
    print("--- going silent 7 s ---")
    time.sleep(7)
    print("--- silence over ---")
    st = b.read_status()
    check(st is not None and st.rev == 2, "STATUS alive after write-abort")
    # barrier (post-crash re-sync, like the library does in open())
    b._barrier_close_flush()
    ci = b.card_info()
    check(ci is not None and ci.mounted == 1, "CARD_INFO mounted after abort")
    check(b.file_size(FILE) == SENT, "FILE_SIZE == 2048 prefix")
    check(b.exists(FILE), "FILE_EXISTS after abort")
    r = b.open(FILE, "r")
    if r is not None:
        data = r.read(SENT)
        ok = data == expect[:SENT]
        r.close()
    else:
        ok = False
    check(ok, "aborted file content = 2048 B prefix")

# Phase 3: read-abort
r = b.open(FILE, "r")
check(r is not None, "OPEN_READ for read-abort")
if r is not None:
    # partial drain 512 B (two reads of 128)
    got = len(r.read(128)) + len(r.read(128))
    check(0 < got < 8192, "partial READ drain before abort")
    print("--- silent mid-READ 7 s ---")
    time.sleep(7)
    print("--- silence over ---")
    # reopen (barrier inside open)
    r.close() if r else None
    r2 = b.open(FILE, "r")
    check(r2 is not None, "OPEN_READ after read-abort")
    if r2 is not None:
        data = r2.read(SENT)
        check(data == expect[:SENT], "full re-read after read-abort")
        r2.close()
else:
    check(False, "partial READ drain before abort")

# Phase 4: fresh round-trip
w = b.open("AbruptAfter.bin", "w")
ok = False
if w is not None:
    w.write(b"X" * 1024)
    w.close()
    r = b.open("AbruptAfter.bin", "r")
    if r is not None:
        ok = len(r.read(1024)) == 1024
        r.close()
check(ok, "fresh 1 KB round-trip after aborts")
print(f"=== {'ABRUPT PASS' if fails == 0 else 'ABRUPT FAIL'} ===")




