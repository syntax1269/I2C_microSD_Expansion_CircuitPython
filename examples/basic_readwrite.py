# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""basic_readwrite — 64 KB flow-paced round-trip + CRC32.

Port of BasicReadWrite.ino for the I²C microSD Expansion. Pattern b[i] = (i*7+3)&0xFF; CRC32 IEEE
poly 0xEDB88320 must equal 0xD660AF09 on the 64 KB test vector.
"""

import time

import board
import busio

from i2c_microsd_module import I2CmicroSD

KBYTES = 65536
PATH = "Example64K.BIN"


def crc_update(crc, data):
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (0xEDB88320 ^ (crc >> 1)) if (crc & 1) else (crc >> 1)
    return crc


i2c = busio.I2C(board.GP1, board.GP0)
microSDexp = I2CmicroSD(i2c, scl_hz=400000)
if not microSDexp.begin():
    print("begin FAILED")
    raise SystemExit

w = microSDexp.open(PATH, "w")
if w is None:
    print('open "w" FAILED')
    raise SystemExit

t0 = time.monotonic()
chunk = bytearray(64)
for off in range(0, KBYTES, 64):
    for i in range(64):
        chunk[i] = ((off + i) * 7 + 3) & 0xFF
    if w.write(chunk) != 64:
        print("fileWrite short")
        raise SystemExit
if not w.close():
    print("fileClose (write) FAILED")
    raise SystemExit
print(f"wrote {KBYTES} B in {time.monotonic() - t0:.2f} s")

r = microSDexp.open(PATH, "r")
if r is None:
    print('open "r" FAILED')
    raise SystemExit

crc = 0xFFFFFFFF
got = 0
mism = 0
buf = bytearray(256)
while got < KBYTES:
    # Ask for a full v18.8.21 drain (both of the module's 128 B TX buffers);
    # read() chunks internally if the bus carries less.
    want = min(256, KBYTES - got)
    data = r.read(want)
    if not data:
        break
    for i, b in enumerate(data):
        if b != (((got + i) * 7 + 3) & 0xFF):
            mism += 1
    crc = crc_update(crc, data)
    got += len(data)
r.close()
hashv = crc ^ 0xFFFFFFFF
print(f"read {got} B mismatches={mism} hash={hashv:08X}")
print("BasicReadWrite: PASS" if got == KBYTES and mism == 0 and hashv == 0xD660AF09 else "BasicReadWrite: FAIL")




