# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT
"""Non-blocking write using the submit/poll API (no sleeps)."""

import time

import board
import busio

from i2c_microsd_module import I2CmicroSD, AsyncOp, ASYNC_BUSY, ASYNC_OK

i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
microSDexp = I2CmicroSD(i2c, address=0x6E, scl_hz=400000)
if not microSDexp.begin():
    raise SystemExit("module not found")

payload = bytes((i * 7 + 3) & 0xFF for i in range(512))

op = AsyncOp()
if not microSDexp.begin_open_write("ASYNC.BIN", op):
    raise SystemExit("submit failed")
while microSDexp.poll_op(op) == ASYNC_BUSY:
    pass  # do other work here

sent = 0
while sent < len(payload):
    n = microSDexp.write_now(payload[sent:])
    if n:
        sent += n
    else:
        pass  # module busy -- do other work, then retry

target = microSDexp.committed_bytes()
while microSDexp.committed_bytes() < target:
    pass

op = AsyncOp()
if microSDexp.begin_close(op):
    while microSDexp.poll_op(op) == ASYNC_BUSY:
        pass
print("non-blocking write done")
