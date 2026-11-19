# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""simpletest — probe the I²C microSD Expansion module and print STATUS/card info.

Copy onto CIRCUITPY as code.py (or run from the REPL). Sketch owns the
bus; the library only probes.
"""

import board
import busio

from i2c_microsd_module import I2CmicroSD

# Device 1 — adjust SCL/SDA to your board.
i2c = busio.I2C(board.GP1, board.GP0)
microSDexp = I2CmicroSD(i2c, scl_hz=400000)

if microSDexp.begin():
    st = microSDexp.read_status()
    print(f"microSDexp OK rev={st.rev} state={st.state} opDone={st.op_done}")
    print(f"version: {microSDexp.version()!r}")
    info = microSDexp.card_info()
    if info is not None:
        print(
            f"card mounted={info.mounted} fat={info.fat_type} "
            f"sectors={info.sector_count} free_clusters={info.free_clusters}"
        )
    print(f"tempK raw: {microSDexp.temperature_k()}")
else:
    print("microSD begin FAILED (check wiring / 0x6E)")




