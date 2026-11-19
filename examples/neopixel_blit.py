# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""neopixel_blit — drive a WS2812B strip from the module's bit-bang engine.

Port of NeoPixelBlit.ino. The module bit-bangs one expansion pin; the
library pushes raw GRB bytes into its 256-byte frame workspace and profile
0x01 latches them. No LED library and no host-side timing.

Wiring (module expansion header -> strip):
  DATA  -> strip DIN (through ~330 ohm)   GND -> GND   V+ -> 3.3 V or 5 V
  1000 uF across the strip supply. A 5 V strip needs a level shifter on
  DIN, because the module's pins are 3.3 V logic.

Three rules the library cannot enforce:
  1. the pin must be a digital output first (set_pin_mode(pin, 0));
  2. clear the workspace before a shorter frame, or leftover bytes from a
     longer earlier frame light extra pixels;
  3. leave a frame time (~30 us/pixel + latch reset) before the next I2C
     command -- the module clocks the frame out after it ACKs the execute.
"""

import time

import board
import busio

from i2c_microsd_module import I2CmicroSD, protocol

# Pick the pin your board's expansion header exposes.
NEO_PIN = protocol.MICROSDEXP_PIN_PA5  # or MICROSDEXP_PIN_PB2 / MICROSDEXP_PIN_PB3
NEO_COUNT = 8  # pixels in your strip (max 85 -- 255 of the 256 B workspace)
FRAME_S = 0.002 + (NEO_COUNT * 32) / 1000000.0

i2c = busio.I2C(board.IO1, board.IO2, frequency=400000)
microSDexp = I2CmicroSD(i2c, scl_hz=400000)
if not microSDexp.begin():
    raise SystemExit("neopixel_blit: microSD expansion not found")

if not microSDexp.set_pin_mode(NEO_PIN, 0):  # 0 = digital output
    raise SystemExit("neopixel_blit: set_pin_mode failed (PA5, PB2 or PB3)")
time.sleep(0.150)  # the mode change queues an EEPROM write on the module
microSDexp.bitbang_clear()

frame = bytearray(NEO_COUNT * 3)  # GRB per pixel, green first


def fill(red, green, blue):
    for px in range(NEO_COUNT):
        frame[px * 3 + 0] = green
        frame[px * 3 + 1] = red
        frame[px * 3 + 2] = blue


def show():
    ok = microSDexp.show_neopixels(NEO_PIN, frame)
    time.sleep(FRAME_S)  # let the module finish the blit
    return ok


ok = True

# 1. all off
fill(0, 0, 0)
ok = show() and ok
time.sleep(0.3)

# 2. the three primaries, so the G/R/B order is easy to confirm
for red, green, blue in ((255, 0, 0), (0, 255, 0), (0, 0, 255)):
    fill(red, green, blue)
    ok = show() and ok
    time.sleep(0.4)

# 3. a dim green dot chasing round the strip, twice
for _ in range(2):
    for px in range(NEO_COUNT):
        fill(0, 0, 0)
        frame[px * 3 + 1] = 24  # ~10 % green
        ok = show() and ok
        time.sleep(0.09)

# 4. all off again
fill(0, 0, 0)
ok = show() and ok

print("NeoPixelBlit: PASS" if ok else f"NeoPixelBlit: FAIL err={microSDexp.last_error}")
