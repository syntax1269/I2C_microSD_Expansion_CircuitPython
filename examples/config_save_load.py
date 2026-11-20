# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""config_save_load — persistent settings with checked queries and safe update.

Shows exists_checked()/file_size_checked(): "missing" is not confused with an
I2C/card error. A new config is staged in CONFIG.TMP, the live file is removed,
then the staged bytes are rewritten as CONFIG.INI. The module has no atomic
rename, so the config carries a checksum: a power loss in the small remove /
rewrite window is detected at boot and falls back to defaults, never to a
half-written setting that the sketch would act on.
"""

import board
import busio

from i2c_microsd_module import I2CmicroSD

CFG_PATH = "CONFIG.INI"
TMP_PATH = "CONFIG.TMP"

i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
microSDexp = I2CmicroSD(i2c, address=0x6E, scl_hz=400000)
if not microSDexp.begin():
    raise SystemExit("config_save_load: module not found")


def checksum(prefix):
    """XOR of every byte in prefix."""
    value = 0
    for b in prefix:
        value ^= b
    return value


def format_config(threshold, interval_ms):
    prefix = f"T={threshold},I={interval_ms},"
    return f"{prefix}X={checksum(prefix.encode('ascii')):02X}\n"


def parse_config(text):
    try:
        mark = text.index("X=")
        expected = int(text[mark + 2 :].strip(), 16)
        if expected != checksum(text[:mark].encode("ascii")):
            return None
        threshold = int(text[text.index("T=") + 2 :].split(",")[0])
        interval = int(text[text.index("I=") + 2 :].split(",")[0])
        return (threshold, interval)
    except (ValueError, IndexError):
        return None


def write_all(path, text):
    """Write a complete file in one open/write/close sequence."""
    try:
        with microSDexp.open(path, "w") as f:
            return f.write(text.encode("ascii"))
    except OSError:
        return False


def stage_and_install(text):
    """Write to temp, retire the old file, install the fully staged bytes."""
    if not write_all(TMP_PATH, text):
        return False
    # A fresh card has no live file yet; REMOVE_FILE on a missing path errors.
    ok, present = microSDexp.exists_checked(CFG_PATH)
    if not ok:
        return False
    if present and not microSDexp.remove(CFG_PATH):
        return False
    if not write_all(CFG_PATH, text):
        return False
    microSDexp.remove(TMP_PATH)  # best-effort cleanup
    return True


def load_config():
    ok, present = microSDexp.exists_checked(CFG_PATH)
    if not ok:
        print("config_save_load: exists_checked FAILED (bus/card error)")
        return None
    if not present:
        return None
    ok, size = microSDexp.file_size_checked(CFG_PATH)
    if not ok or size == 0 or size > 63:
        return None
    try:
        with microSDexp.open(CFG_PATH, "r") as f:
            raw = f.read(size)
    except OSError:
        return None
    return parse_config(raw.decode("ascii", "ignore"))


cfg = load_config()
if cfg is None:
    cfg = (512, 250)
    if not stage_and_install(format_config(*cfg)):
        raise SystemExit("config_save_load: failed to create defaults")
    print("config_save_load: created default config")
else:
    print("config_save_load: loaded existing config")

print(format_config(*cfg).rstrip())

# A settings change: bump the threshold and persist it safely.
cfg = (768, cfg[1])
if stage_and_install(format_config(*cfg)):
    print("config_save_load: settings updated")
else:
    print("config_save_load: update FAILED — boot will fall back to defaults")
