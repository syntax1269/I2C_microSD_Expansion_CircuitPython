# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""sensor_ring_logger — high-frequency logging with a local SRAM ring buffer.

Port of SensorRingLogger.ino. A 500 Hz producer fills a 512-byte ring while
write_now() drains it as fast as the module accepts bytes. When the module is
busy (flash-page erase) write_now() returns 0 and the samples simply wait in
the ring: no SD-card stall ever delays the sampling loop.

Adjust the SCL/SDA pins below for your board.
"""

import time

import board
import busio

from i2c_microsd_module import I2CmicroSD, AsyncOp, ASYNC_BUSY, ASYNC_OK

SAMPLE_S = 0.002       # 500 Hz
RUN_S = 10.0
RING_BYTES = 512       # 128 samples x 4 bytes = 256 ms of slack
MASK = RING_BYTES - 1  # power of two -> cheap wrap

i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
microSDexp = I2CmicroSD(i2c, address=0x6E, scl_hz=400000)
if not microSDexp.begin():
    raise SystemExit("sensor_ring_logger: module not found")

op = AsyncOp()
if not microSDexp.begin_open_write("SENSOR.CSV", op):
    raise SystemExit("sensor_ring_logger: open submit failed")
while microSDexp.poll_op(op) == ASYNC_BUSY:
    pass
if microSDexp.poll_op(op) != ASYNC_OK:
    raise SystemExit("sensor_ring_logger: open failed")

baseline = microSDexp.committed_bytes()
ring = bytearray(RING_BYTES)
head = tail = used = 0
produced = dropped = pushed = 0
next_sample = start = time.monotonic()

print("sensor_ring_logger: sampling at 500 Hz for 10 s")
while True:
    now = time.monotonic()

    # ---- Producer: one 4-byte sample every 2 ms ---------------------------
    if now >= next_sample:
        next_sample += SAMPLE_S
        if next_sample < now:  # we fell behind: resync, do not burst-catch-up
            next_sample = now + SAMPLE_S
        tick = int(now * 1000)
        value = 512 + ((tick // 4) & 0x3FF)  # simulated 10-bit sensor
        sample = bytes((tick & 0xFF, (tick >> 8) & 0xFF,
                        value & 0xFF, (value >> 8) & 0xFF))
        if used + len(sample) <= RING_BYTES:
            for byte in sample:
                ring[head] = byte
                head = (head + 1) & MASK
            used += len(sample)
            produced += 1
        else:
            dropped += 1  # an SD erase outlasted the ring's slack

    # ---- Consumer: push only what RX can accept right now -----------------
    if used:
        n = min(used, 64, RING_BYTES - tail)
        chunk = bytes(ring[tail : tail + n])
        accepted = microSDexp.write_now(chunk)
        if accepted:
            tail = (tail + accepted) & MASK
            used -= accepted
            pushed += accepted
        # 0 = module busy: leave the bytes in the ring and retry next pass

    # ---- Finish: drain, wait for commit, close ---------------------------
    if now - start >= RUN_S and used == 0:
        while microSDexp.committed_bytes() < baseline + pushed:
            pass
        op = AsyncOp()
        if microSDexp.begin_close(op):
            while microSDexp.poll_op(op) == ASYNC_BUSY:
                pass
            ok = microSDexp.poll_op(op) == ASYNC_OK
        else:
            ok = False
        print(f"sensor_ring_logger: {'DONE' if ok else 'CLOSE ERROR'} "
              f"produced={produced} dropped={dropped} pushed={pushed}")
        break
