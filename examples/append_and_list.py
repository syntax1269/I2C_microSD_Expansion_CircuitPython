# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""list_dir + append + queries for the I²C microSD Expansion (M2 legacy surface)."""

import board
import busio

from i2c_microsd_module import I2CmicroSD

i2c = busio.I2C(board.GP1, board.GP0)
microSDexp = I2CmicroSD(i2c, scl_hz=400000)
if not microSDexp.begin():
    print("begin FAILED")
    raise SystemExit

print(f"version: {microSDexp.version()!r}")

entries = microSDexp.list_dir("/")
print(f"/ contains {len(entries)} entries")
for e in entries:
    print(f"  {'D' if e.is_dir else 'F'} {e.name!r} {e.size}")

f = microSDexp.open("NANO.TXT", "a")
if f is not None:
    f.write(b"hello circuitpython\n")
    f.close()
    print("append OK")

print(f"size NANO.TXT = {microSDexp.file_size('NANO.TXT')}")
print(f"exists NANO.TXT = {microSDexp.exists('NANO.TXT')}")
print(f"isDir / = {microSDexp.is_directory('/')}")




