# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""bitbang_script — run a token script on the module (bit-bang profile 0x02).

Port of BitBangScript.ino. The script lives in the module's 256-byte
workspace and the module plays it itself after the execute command, so the
host is not involved while it runs: that is how to make timed edges that
I2C latency would blur.

Wiring: whatever the pin should drive -- an LED with a series resistor to
GND, a scope probe, a small piezo, or a NeoPixel data line.

Script tokens (bridge firmware v18.5.2 and up):
  0x01              SET_HIGH
  0x02              SET_LOW
  0x03  usL usH     DELAY_US     1..65535 us, counted in CPU cycles
  0x04  ms          DELAY_MS     1..255 ms
  0x05  target cnt  LOOP_GOTO    jump to byte offset <target>, <cnt> passes
  0x00 (or any unrecognised byte) ends the script

Rules:
  1. put the pin in digital-output mode (set_pin_mode) and select it for the
     engine (bitbang_set_mode) first;
  2. clear the workspace before buffering, or the script runs on into
     whatever the previous script left behind;
  3. the module masks its millis tick while the script plays and its
     watchdog is 8.2 s: keep scripts short, and start no I2C traffic until
     the script has finished (the sleep after each play below).
"""

import time

import board
import busio

from i2c_microsd_module import I2CmicroSD, protocol

BB_PIN = protocol.MICROSDEXP_PIN_PA5  # or MICROSDEXP_PIN_PB2 / MICROSDEXP_PIN_PB3

# Blink: 200 ms high, 200 ms low, five passes (2 s).
# Offsets: 0 SET_HIGH, 1 DELAY_MS(200), 3 SET_LOW, 4 DELAY_MS(200),
#          6 LOOP_GOTO(target 0, 5 passes)
BLINK = bytes(
    [
        0x01, 0x04, 200,  # SET_HIGH, DELAY_MS 200
        0x02, 0x04, 200,  # SET_LOW,  DELAY_MS 200
        0x05, 0x00, 5,  # LOOP_GOTO target 0, five passes
    ]
)

# Burst: twenty 1 ms pulses, then the line idles low.
# Offsets: 0 SET_HIGH, 1 DELAY_US(1000), 4 SET_LOW, 5 DELAY_US(1000),
#          8 LOOP_GOTO(target 0, 20 passes)
BURST = bytes(
    [
        0x01, 0x03, 0xE8, 0x03,  # SET_HIGH, DELAY_US 1000
        0x02, 0x03, 0xE8, 0x03,  # SET_LOW,  DELAY_US 1000
        0x05, 0x00, 20,  # LOOP_GOTO target 0, twenty passes
    ]
)

i2c = busio.I2C(board.IO1, board.IO2, frequency=400000)
microSDexp = I2CmicroSD(i2c, scl_hz=400000)
if not microSDexp.begin():
    raise SystemExit("bitbang_script: microSD expansion not found")

if not microSDexp.set_pin_mode(BB_PIN, 0):  # 0 = digital output
    raise SystemExit("bitbang_script: set_pin_mode failed (PA5, PB2 or PB3)")
time.sleep(0.150)  # the mode change queues an EEPROM write on the module
if not microSDexp.bitbang_set_mode(BB_PIN):
    raise SystemExit("bitbang_script: bitbang_set_mode failed")
microSDexp.bitbang_clear()  # no stale tokens behind the scripts below


def play(script, play_s):
    """Buffer one script and play it once, then wait it out."""
    if not microSDexp.bitbang_buffer(0, script):
        print(f"  buffer FAILED err={microSDexp.last_error}")
        return False
    if not microSDexp.bitbang_execute(protocol.MICROSDEXP_BITBANG_PROFILE_SCRIPT):
        print(f"  execute FAILED err={microSDexp.last_error}")
        return False
    time.sleep(play_s)  # the module is playing: keep the bus quiet
    return True


print("BitBangScript: 5 x 200 ms blink (2 s)")
ok = play(BLINK, 2.1)
time.sleep(0.2)

print("BitBangScript: 20 x 1 ms pulse burst (40 ms)")
microSDexp.bitbang_clear()
ok = play(BURST, 0.1) and ok

print("BitBangScript: PASS" if ok else "BitBangScript: FAIL")
