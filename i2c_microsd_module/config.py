# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""config — sketch knobs (mirror of the Arduino I2C_microSD_Expansion_Config.h).

Timeout scaling: ``timeoutScaled = base * 100000 / scl_hz``, but never
below ``base`` (worker time does not track the I2C clock). Ops below
50 kHz Sm are forced to >= 2x, capped at 120 s.
"""

DEFAULT_ADDRESS = 0x6E

# Master push size. module blocks are 128 B; 64 B stays inside every
# CircuitPython I2C transaction buffer (RP2040/nRF/ESP32-S3).
CHUNK_BYTES = 64
# Bytes requested per READ drain. Firmware v18.8.21 stages up to 256 B across
# both module TX buffers; busio sizes transactions per call, but a port that
# caps a single transfer lower (e.g. nRF TWIM at 255) is handled by an
# automatic 128 B fallback in microSDexp.read().
READ_CHUNK_BYTES = 256

POLL_MS = 10
FLOW_POLL_MS = 2

OP_TIMEOUT_MS = 15000
COMMIT_TIMEOUT_MS = 30000
# A real FAT rebuild takes tens of seconds on a large card, so format() waits
# on its own budget instead of OP_TIMEOUT_MS (mirrors the Qwiic driver).
FORMAT_TIMEOUT_MS = 300000
# CMD_VERSION answers with a fixed 112 B banner buffer on firmware >= 18.8.0;
# older firmware returns the bare version string followed by NUL padding.
VERSION_BANNER_BYTES = 112

# Normal LFN path cap. Tinyi2cStorage / 328p AVR Wire caps (25/31) have no
# CircuitPython equivalent — CircuitPython buses buffer >= 128 B, so the
# full LFN limit applies here.
PATH_MAX = 260

# Bit-bang frame/script payload per workspace write. One write is the command
# byte + 3 header bytes (offset LSB, offset MSB, length) + payload, all in a
# single bus transaction, so 120 keeps every core's buffer happy (the Arduino
# library uses the same figure off AVR). The module workspace is 256 B.
BITBANG_MAX = 120




