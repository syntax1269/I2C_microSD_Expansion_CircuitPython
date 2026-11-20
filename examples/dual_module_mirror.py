# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""dual_module_mirror — two modules, one bus, automatic failover.

Port of DualModuleMirror.ino. moduleA is at 0x6E, moduleB at 0x6C. Every
frame is appended to both cards; when a sticky_error() appears on Card A the
sketch keeps logging to Card B without dropping frames.

Provisioning (one time): both modules ship at 0x6E. Set PROVISION_MODULE_B
below to True, DISCONNECT MODULE A first, run once and confirm, then reconnect
A and set the flag back to False. The address command changes every module
still at 0x6E, so never run it with both modules attached.
Adjust SCL/SDA for your board.
"""

import time

import board
import busio

from i2c_microsd_module import I2CmicroSD

# One-time provisioning. True ONLY for one run, after disconnecting module A.
PROVISION_MODULE_B = False


def provision_module_b(bus):
    """Set the single remaining module's address to 0x6C and persist it."""
    print("PROVISION: disconnect module A from the I2C bus now.")
    answer = input("Type Y and Enter to set the remaining module to 0x6C: ")
    if answer.strip().upper() != "Y":
        print("PROVISION: cancelled - no address was changed")
        return False
    bus.writeto(0x6E, bytes([0x16, 0x6C]))  # CMD_I2C_SET_ADDR
    time.sleep(0.02)                        # module applies it from STOP
    bus.writeto(0x6C, bytes([0x1A]))        # CMD_SAVEEEPROM
    print("PROVISION: module B is now 0x6C (saved to EEPROM).")
    print("PROVISION: reconnect module A, then reset the board.")
    return True


i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
if PROVISION_MODULE_B and not provision_module_b(i2c):
    raise SystemExit("dual_module_mirror: provisioning aborted")

card_a = I2CmicroSD(i2c, address=0x6E, scl_hz=400000)
card_b = I2CmicroSD(i2c, address=0x6C, scl_hz=400000)

a_up = card_a.begin()
b_up = card_b.begin()
if not a_up:
    print("dual_module_mirror: module A (0x6E) not found")
if not b_up:
    print("dual_module_mirror: module B (0x6C) not found")

# Start with a clean latch so the first real failure is easy to spot.
card_a.clear_error()
card_b.clear_error()
print(f"A: {'UP' if a_up else 'DOWN'} addr=0x6E "
      f"sticky={card_a.sticky_error}")
print(f"B: {'UP' if b_up else 'DOWN'} addr=0x6C "
      f"sticky={card_b.sticky_error}")

frame_no = 0
while a_up or b_up:
    frame_no += 1
    frame = f"{frame_no},{time.monotonic()}\n".encode("ascii")

    if a_up:
        try:
            with card_a.open("MIRROR.CSV", "a") as f:
                f.write(frame)
        except OSError:
            pass
        if not card_a.last_ok or card_a.sticky_error != 0:
            a_up = False
            print("dual_module_mirror: Card A FAILED -> failing over to B")
            print(f"A: DOWN sticky={card_a.sticky_error}")

    if b_up:
        try:
            with card_b.open("MIRROR.CSV", "a") as f:
                f.write(frame)
        except OSError:
            pass
        if not card_b.last_ok or card_b.sticky_error != 0:
            b_up = False
            print("dual_module_mirror: Card B FAILED")
            print(f"B: DOWN sticky={card_b.sticky_error}")

    print(f"frame {frame_no} -> {'A+B' if a_up else 'B only'}")
    time.sleep(0.5)

if not (a_up or b_up):
    raise SystemExit("dual_module_mirror: no module available")
