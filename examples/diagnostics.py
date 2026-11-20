# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT
"""Print a one-page health report from the I2C microSD Expansion module."""

import board
import busio

from i2c_microsd_module import I2CmicroSD

i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
microSDexp = I2CmicroSD(i2c, address=0x6E, scl_hz=400000)

if not microSDexp.begin():
    print("Module not found - showing partial diagnostics anyway")

print(microSDexp.diagnostics())
