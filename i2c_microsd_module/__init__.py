# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""i2c_microsd_module — host library for the I²C microSD Expansion.

CircuitPython port of the I²C microSD Expansion Arduino host library
(Arduino ``Wire`` library). Requires module firmware >= 18.7.6
(protocol rev 2) for the file API; the pin/bit-bang API needs >= 18.5.2,
and buffered-frame-only NeoPixel output (a cleared workspace goes dark)
needs >= 18.8.0.

The sketch owns the I2C bus (like ``Wire.begin()`` on Arduino)::

    import board, busio
    from i2c_microsd_module import I2CmicroSD

    i2c = busio.I2C(board.GP1, board.GP0)  # device1
    microSDexp = I2CmicroSD(i2c, scl_hz=400000)
    microSDexp.begin()

The library itself has no ``print()`` calls — all output is sketch-owned,
mirroring the Arduino library rule (zero ``Serial`` in ``src/``).
"""

from .module import (
    MicroSDExpError,
    MicroSDExpFile,
    CardInfo,
    DirEntry,
    I2CmicroSD,
    StatusFrame,
    open_file,
    AsyncOp,
    ASYNC_OK,
    ASYNC_BUSY,
    ASYNC_IOERR,
)
from . import protocol
from . import config

__version__ = "1.0.9"
__repo__ = "https://github.com/syntax1269/I2C_microSD_Expansion_CircuitPython"

__all__ = [
    "MicroSDExpError",
    "MicroSDExpFile",
    "CardInfo",
    "DirEntry",
    "I2CmicroSD",
    "StatusFrame",
    "open_file",
    "AsyncOp",
    "ASYNC_OK",
    "ASYNC_BUSY",
    "ASYNC_IOERR",
    "protocol",
    "config",
    "__version__",
]




