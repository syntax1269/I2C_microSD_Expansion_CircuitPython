# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""protocol — wire constants for I²C microSD Expansion rev 2 (fw >= 18.7.6).

Byte-for-byte mirror of ``protocol.h`` in the Arduino library.
"""

# ---- Legacy command family (0x01-0x0B, 0x0E) ----
MICROSDEXP_CMD_FILENAME = 0x01  # write: filename bytes; STOP stores path
MICROSDEXP_CMD_WRITE_FILE = 0x02  # write: payload + STOP -> create/overwrite, write, close
MICROSDEXP_CMD_READ_FILE = 0x03  # STOP -> open for read, stream via TX buffers
MICROSDEXP_CMD_APPEND_FILE = 0x04  # write: payload + STOP -> append, write, close
MICROSDEXP_CMD_FILE_SIZE = 0x05  # STOP -> size (4 B LE) in STATUS.result
MICROSDEXP_CMD_FILE_EXISTS = 0x06  # STOP -> 1=exists, 0=not found in STATUS.result
MICROSDEXP_CMD_IS_DIRECTORY = 0x07  # STOP -> 1=directory, 0=not in STATUS.result
MICROSDEXP_CMD_LIST_DIR = 0x08  # STOP -> TX-stream entries: 'F'/'D' + NUL basename + 4 B size LE, 0xFF term (v18.7.6)
MICROSDEXP_CMD_MAKE_DIR = 0x09  # STOP -> create directory at Filename
MICROSDEXP_CMD_REMOVE_DIR = 0x0A  # STOP -> remove empty directory
MICROSDEXP_CMD_REMOVE_FILE = 0x0B  # STOP -> delete file at Filename
MICROSDEXP_CMD_CLOCK_SET = 0x0E  # write: 6 B [Y,M,D,h,m,s]; STOP applies
MICROSDEXP_CMD_VERSION = 0x0F  # read: NUL-free version string ("18.7.6")

# ---- Pin / extension commands ----
MICROSDEXP_CMD_PA5_SET_MODE = 0x10
MICROSDEXP_CMD_PA5_CONTROL = 0x11
MICROSDEXP_CMD_PB2_SET_MODE = 0x12
MICROSDEXP_CMD_PB2_CONTROL = 0x13
MICROSDEXP_CMD_PB3_SET_MODE = 0x14
MICROSDEXP_CMD_PB3_CONTROL = 0x15
MICROSDEXP_CMD_I2C_SET_ADDR = 0x16
MICROSDEXP_CMD_TEMP_READ = 0x17  # read: temperature
MICROSDEXP_CMD_ADC_READ_PA5 = 0x18  # read: 12-bit ADC (PA5)
MICROSDEXP_CMD_ADC_READ_PB3 = 0x19
MICROSDEXP_CMD_SAVEEEPROM = 0x1A  # STOP -> persist pin modes + I2C addr to EEPROM (explicit only)
MICROSDEXP_CMD_PIN_STATE_READ = 0x1C

# ---- Async protocol (rev 2) ----
MICROSDEXP_CMD_STATUS = 0x20  # read: 12-byte status frame
MICROSDEXP_CMD_OPEN_WRITE = 0x21  # write: filename bytes; STOP enqueues OPEN (RDWR, truncate)
MICROSDEXP_CMD_WRITE = 0x22  # write: payload block -> RX buffers
MICROSDEXP_CMD_READ = 0x23  # write: request block; read: drain TX buffer
MICROSDEXP_CMD_CLOSE_FLUSH = 0x24  # write: STOP enqueues CLOSE (flush + close)
MICROSDEXP_CMD_OPEN_READ = 0x25  # write: filename bytes; STOP enqueues OPEN (read-only)
MICROSDEXP_CMD_DIAG = 0x26
MICROSDEXP_CMD_DIAG2 = 0x27
MICROSDEXP_CMD_FORMAT = 0x28  # write: 1 B mode (0=auto, 1=force FAT); STOP enqueues format
MICROSDEXP_CMD_CARD_INFO = 0x29  # read: 24-byte card/volume snapshot (LE always)
MICROSDEXP_CMD_SD_DIAG = 0x2A
MICROSDEXP_CMD_BITBANG_SET_MODE = 0x2B
MICROSDEXP_CMD_BITBANG_BUFFER = 0x2C
MICROSDEXP_CMD_BITBANG_EXECUTE = 0x2D
MICROSDEXP_CMD_BITBANG_CLEAR = 0x2E
MICROSDEXP_CMD_REBOOT = 0x2F  # write: reboot module (WDT reset from loop)

# ---- Module expansion pin IDs (bit-bang and pin control) ----
MICROSDEXP_PIN_PA5 = 5
MICROSDEXP_PIN_PB2 = 2
MICROSDEXP_PIN_PB3 = 3

# ---- Bit-bang engine profiles ----
MICROSDEXP_BITBANG_PROFILE_NEOPIXEL = 0x01
MICROSDEXP_BITBANG_PROFILE_SCRIPT = 0x02

# Frame/script workspace on the module (bytes). Bytes addressed past it are
# dropped, so a NeoPixel frame is at most 255 B (85 pixels).
BITBANG_WORKSPACE_SIZE = 256

# ---- STATUS.state ----
MICROSDEXP_ST_IDLE = 0
MICROSDEXP_ST_ACCEPTED = 1
MICROSDEXP_ST_BUSY_RX = 2
MICROSDEXP_ST_BUSY_SD = 3
MICROSDEXP_ST_TX_READY = 4
MICROSDEXP_ST_COMPLETE = 5
MICROSDEXP_ST_ERROR = 6
MICROSDEXP_ST_OVERFLOW = 7

# ---- STATUS.error ----
MICROSDEXP_ERR_NONE = 0
MICROSDEXP_ERR_NO_FILE = 1
MICROSDEXP_ERR_OPEN = 2
MICROSDEXP_ERR_CARD = 3
MICROSDEXP_ERR_QUEUE = 4
MICROSDEXP_ERR_INVALID = 5
MICROSDEXP_ERR_OVERFLOW = 6

# listDir stream terminator
LIST_END = 0xFF




