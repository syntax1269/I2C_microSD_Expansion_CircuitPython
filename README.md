# I²C microSD Expansion — CircuitPython Library

**Add FAT file storage to any CircuitPython board with just two wires.**

The [I²C microSD Expansion](https://github.com/syntax1269/I2C-microSD-Expansion) module owns
the SD card and the FAT filesystem. Your CircuitPython code talks to it over I²C:
open a file, write bytes, read them back, list directories — with no FAT stack, SD
driver, or level shifter in your code. The module also exposes three expansion
pins and a bit-bang engine that can drive WS2812B strips or run timed pin scripts
on its own.

This is the **CircuitPython port**. The same API and the same `microSDexp`
instance name are available in the
[Arduino](https://github.com/syntax1269/I2C-microSD-Expansion)
and [Qwiic Python](https://github.com/syntax1269/I2C_microSD_Expansion_Qwiic_Py)
ports.

---

## Why use this module?

| Task | Without the module | With the module |
|---|---|---|
| Write a log | FAT library + SPI + 4+ pins + shifter | `microSDexp.open("log.csv", "a")` → `write()` → `close()` |
| Read a file | Same, plus RAM for buffers | `microSDexp.open("data.bin", "r")` → `read()` |
| List a directory | FAT directory parsing | `microSDexp.list_dir("/")` |
| Check card health | Mount volume, parse CSD | `microSDexp.card_info()` |
| Long filenames | LFN code size | Works out of the box (259-char paths) |
| WS2812B strip | LED library + PIO/RMT + pins | `microSDexp.show_neopixels(pin, grb, count)` |

One file can be open at a time. `close()` and `sync()` return only after the
bytes are committed to the card.

---

## Requirements

- A CircuitPython board with an I²C bus (`busio.I2C`).
- An I²C microSD Expansion module with a FAT16/FAT32-formatted microSD card.
- Module firmware **18.5.x+** for files, **18.5.2+** for pins/bit-bang, and
  **18.8.0+** for banner-only frames and the measured-clock report. Check with
  `microSDexp.version()`.

---

## Install

1. Copy the `i2c_microsd_module/` folder into `lib/` on your `CIRCUITPY` drive.
2. `adafruit_bus_device` ships with CircuitPython 6.3 and newer. If your board
   lacks `lib/adafruit_bus_device/`, add it from the official CircuitPython
   library bundle.
3. Save your program as `code.py` (or any `*.py`) on `CIRCUITPY`.

On a Linux/RPi host with Blinka, the same library installs from PyPI:

```sh
pip install i2c-microsd-expansion-circuitpython
```

For packaging a single zip, `pyproject.toml` and `requirements.txt` are included
so the module can be built with `circuitpython-build-tools`.

---

## Wiring

| Board | Module |
|---|---|
| SDA | SDA |
| SCL | SCL |
| GND | GND |
| 3.3 V **or** 5 V | Power (one only, never both) |

- The module handles 3.3 V / 5 V bus logic — no external level shifter.
- 3.3 kΩ pull-ups are fitted on the module; remove them via the underside trace
  cut if your host supplies its own.
- Power from 5 V *or* 3.3 V, never both. The expansion pins are 3.3 V logic;
  a 5 V LED strip needs a level shifter on DIN.

See [docs/wiring.md](docs/wiring.md) for board-specific pin notes.

---

## Quick start

```python
import board
import busio
from i2c_microsd_module import I2CmicroSD

# Use the SCL/SDA pins for your board, e.g. board.IO1/board.IO2 on
# an ESP32-S3 Super Mini, or board.GP1/board.GP0 on RP2040.
i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
microSDexp = I2CmicroSD(i2c, address=0x6E, scl_hz=400000)

if not microSDexp.begin():
    raise SystemExit("microSD expansion not found")

with microSDexp.open("HELLO.TXT", "w") as f:
    f.write(b"HELLO-WORLD")

with microSDexp.open("HELLO.TXT", "r") as f:
    print(f.read(32))        # b'HELLO-WORLD'
```

The default address is `0x6E`; bus speeds of 100 kHz, 400 kHz, and 1 MHz are
supported. `I2CmicroSD.from_bus(i2c, address=0x6E)` is a convenience builder.

---

## Using the library

### Files

```python
# Write / append / read
with microSDexp.open("data.log", "w") as f:      # create/truncate
    f.write(b"a,b,c\n")
    f.sync()                                      # optional commit

with microSDexp.open("log.csv", "a") as f:        # append
    f.write(b"1,2,3\n")

with microSDexp.open("data.log", "r") as f:
    data = f.read(64)                             # short at EOF

# Explicit openers are also available
microSDexp.open_write("x.bin")
microSDexp.open_read("x.bin")
microSDexp.open_append("log.csv")
```

`write()` flow-paces automatically; `read()` returns `b""` at EOF. The file object
is a context manager, so `with` closes it (and commits writes) for you. The
`MicroSDExpFile` instance exposes its owner as `f.microSDexp`.

### Directories and queries

```python
microSDexp.mkdir("logs")
microSDexp.remove("old.tmp")
microSDexp.rmdir("empty")

if microSDexp.exists("data.bin"):
    size = microSDexp.file_size("data.bin")
    is_dir = microSDexp.is_directory("data.bin")

for entry in microSDexp.list_dir("/", max_entries=32):
    print("D" if entry.is_dir else "F", entry.name, entry.size)
```

### Card and module information

```python
print(microSDexp.version())             # e.g. "18.8.22"
print(microSDexp.firmware_banner())     # full CMD_VERSION answer (18.8.0+)
print(microSDexp.firmware_clock_hz())   # measured module clock, 0 on older FW
print(microSDexp.temperature_k())       # whole kelvin; 0xFFFF on error
print(microSDexp.adc_pa5())             # raw ADC; 0xFFFF on error/unavailable

info = microSDexp.card_info()
print(info.mounted, info.fat_type, info.sector_count, info.sck_hz)
```

`card_info().fat_type` uses SdFat values: `0` unmounted, `12`/`16`/`32` for
FAT12/16/32, `64` for exFAT. `sck_hz` is the negotiated card SPI clock — the best
predictor of throughput. `MICROSDEXP_FAT_*` constants are exported for
comparisons. `temperature_k()` returns whole kelvin (2-byte LE, rounded to integer K),
not an ADC count; subtract 273.15 for °C. Both `temperature_k()` and
`adc_pa5()` return `0xFFFF` on any failure — bus error, short read, or
unavailable ADC channel — so check for it.

### Expansion pins

```python
from i2c_microsd_module import protocol

microSDexp.set_pin_mode(protocol.MICROSDEXP_PIN_PB2, 0)   # mode 0 = digital output
microSDexp.write_pin(protocol.MICROSDEXP_PIN_PB2, 1)      # level 1 = high
microSDexp.write_pin(protocol.MICROSDEXP_PIN_PB2, 0)      # level 0 = low
adc = microSDexp.adc_pa5()                                # PA5 ADC
```

The mode/level literals come from the module protocol (there are no named aliases):
`0` in `set_pin_mode` = digital output; `write_pin(..., 0)` = low,
`write_pin(..., 1)` = high (any nonzero value means high); `format(0)` = automatic,
`format(1)` = force FAT rebuild.

Pin modes apply in RAM only; persist them (and the I²C address) once when final:

```python
microSDexp.save_pin_mode()
```

### WS2812B and bit-bang scripts

```python
import time
from i2c_microsd_module import protocol

frame = bytearray(8 * 3)             # GRB, three bytes per pixel
frame[1] = 40                         # first pixel: a little red
microSDexp.set_pin_mode(protocol.MICROSDEXP_PIN_PA5, 0)   # mode 0 = digital output
microSDexp.bitbang_clear()
microSDexp.show_neopixels(protocol.MICROSDEXP_PIN_PA5, frame, 8)
time.sleep(0.003)                     # keep the bus quiet while it latches
```

The workspace is 256 bytes ⇒ at most 85 pixels. For custom timing, load a token
program with `bitbang_buffer()` and run it with
`bitbang_execute(protocol.MICROSDEXP_BITBANG_PROFILE_SCRIPT)`. Tokens are
`SET_HIGH`, `SET_LOW`, `DELAY_US`, `DELAY_MS`, and `LOOP_GOTO`; see the
[Bit-Bang Engine wiki](wiki/Bit-Bang-Engine.md).

### Housekeeping and errors

```python
microSDexp.set_clock_time(2026, 11, 18, 12, 0, 0)
microSDexp.reboot()
microSDexp.format(0)                    # DESTRUCTIVE; 0 = automatic, 1 = force FAT

if microSDexp.last_error != 0:
    ...
if microSDexp.file_open:
    microSDexp.close()
if microSDexp.sticky_error != 0: ...   # fault since clear_error()
microSDexp.clear_error()              # start a fresh error window
```

`last_error` is the result of the *most recent* call and may be overwritten by
internal calls (for example, a `list_dir()` drain). Use `sticky_error` for the
first failure since `clear_error()` when you need an error that internal traffic
cannot hide. `version()` returns `""` with `INVALID` when the banner cannot be
parsed in the available data.

| Value | `MicroSDExpError` | Meaning |
|---|---|---|
| 0 | `OK` | No error |
| 1 | `NO_MODULE` | Module not responding |
| 2 | `NO_FILE` | No file open |
| 3 | `OPEN_FAIL` | Open rejected |
| 4 | `CARD_ERR` | Card / filesystem error |
| 5 | `QUEUE_FULL` | Module queue full |
| 6 | `INVALID` | Bad argument |
| 7 | `OVERFLOW` | Module buffers full |
| 8 | `TIMEOUT` | Operation timed out |

---

## Performance tips

- Use 1 MHz if your board and wiring support it; 400 kHz is a safe default.
- The negotiated card SPI clock matters more than card capacity. Check
  `card_info().sck_hz`: a 10 MHz card reaches ~30 KiB/s at a 1 MHz bus; a
  1 MHz card sits near 18 KiB/s.
- CircuitPython is the usual limit — one Python transaction per chunk. The
  interpreter typically reaches about half of what a compiled host can. For the
  fastest reads, raise the read chunk:

  ```python
  microSDexp.set_read_chunk_bytes(256)
  ```

  The default is safe on all boards; 256 reduces the number of STATUS polls
  during a bulk read.
- `set_poll_interval(ms)` tunes the STATUS poll pause (default 10 ms).
- Time files after the first one written following a module reset; the card
  re-trains on first use.

---

## Examples

| Example | Shows |
|---|---|
| `basic_readwrite.py` | 64 KB round trip with CRC32 |
| `append_and_list.py` | Append writes, directory listing, queries |
| `simpletest.py` | Probe, version, card info, temperature |
| `neopixel_blit.py` | WS2812B strip via the bit-bang engine |
| `bitbang_script.py` | Token scripts for timed pin edges |
| `sweep.py` | Throughput at 100 kHz / 400 kHz / 1 MHz |
| `exhaustive.py` | Full command-table test (destructive) |
| `abrupt_recovery.py` | Recover from mid-write power loss |
| `diagnostics.py` | One-page health report |
| `nonblocking_write.py` | Non-blocking submit/poll write |
| `sensor_ring_logger.py` | 500 Hz sampling with an SRAM ring buffer |
| `config_save_load.py` | Checked queries and staged settings updates |
| `dual_module_mirror.py` | Two modules, one bus, `sticky_error` failover |
| `threshold_bitbang_alert.py` | CSV logging + module-side strobe alert |

Each example is a standalone program — copy it to `CIRCUITPY` as `code.py`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `begin()` returns False | Wrong pins, no common GND, mixed power | Check the bus; common GND; one supply only |
| Card not mounted | exFAT or unformatted card | Reformat FAT16/FAT32 |
| `TIMEOUT` | Bus too slow | Lower the frequency; timeouts scale with the clock |
| Short reads / NACKs on a Raspberry Pi (Pi 4 or earlier) | Broadcom BSC silicon bug with clock stretching | Add `dtoverlay=i2c-gpio` to `/boot/config.txt`, or use a Pi 5 |
| `OVERFLOW` | Writing faster than the module commits | Slow down; the library flow-paces |
| Short reads | Reading before completion | Use `f.read()` in a loop until it returns `b""` |
| Strip stays dark | Pin not an output / wrong data pin | `set_pin_mode(pin, 0)` first |
| Old pixels remain | Command sent mid-frame | Delay a frame time after `show_neopixels()` |

Deep protocol detail is in the [wiki](wiki/Home.md). For the Broadcom host bug
and its workaround, see
[Clock stretching and Raspberry Pi hosts](wiki/Protocol-Reference.md#clock-stretching-and-raspberry-pi-hosts).

---

## Blocking behavior (important)

Most high-level methods are **synchronous**: they poll the module's STATUS
frame in a `delay()` loop until the operation completes or a timeout expires.
They do not sleep the whole time (the I²C bus stays responsive at the protocol
level), but your sketch/application **is blocked** for the duration. Plan for
this with watchdogs, real-time loops, cooperative schedulers and ESP32 tasks.

Timeouts scale up on slow buses (`base × 100000 / I2C_Hz`, floor `base`, 2× below
50 kHz) and are **capped at 120 s** by the host. `format()` is the exception: it
uses an unscaled 300 s budget. The ESP32 gateway's `cardinfo` shows the
configured bus clock.

| Method | Typical wait | Worst case |
|---|---|---|
| `begin()` | ~1.5 s | 10 mount attempts × 150 ms + STATUS probes |
| `read_status()` | one I²C transaction | no loop |
| `wait_for_op_complete()` | 15 s | 120 s cap |
| `wait_for_committed()` | 30 s | 120 s cap |
| `open_write()` / `open_read()` | one op wait | up to 6 × (close-flush barrier + op wait + 200 ms) — potentially minutes |
| `open_append()` | none | local state only |
| `write()` | ~0.8 s per 64 B block (flow poll) | 400 attempts × 2 ms per block; append adds one op wait per chunk |
| `read()` | until bytes arrive | 30 s, up to 120 s cap |
| `sync()` | until bytes commit | 30 s, up to 120 s cap |
| `close()` | sync + one op wait | ~45 s typical, up to two capped waits |
| `format()` | destructive, long | 300 s (unscaled; not subject to the 120 s cap) |
| `mkdir/rmdir/remove/exists/is_directory/file_size/version/firmware_banner/card_info/list_dir` | one op wait | 15 s, up to 120 s cap |
| `bitbang_*()` / `show_neopixels()` / `save_pin_mode()` | one I²C transaction | module-side execution is not awaited |
| `diagnostics()` | a few STATUS reads | no wait loops |

Feed any hardware watchdog around `format()` and the open/write/sync/close
group. If you cannot afford to block, use the non-blocking API below (no feature flag needed).

## Checked queries (return semantics)

`exists()` / `file_size()` / `is_directory()` return a value even when the I²C
command fails, so `False` / `0` can mean either "no such file" or "communication
error". Use the checked variants when that distinction matters — they return
`(ok, value)`:

```python
ok, present = microSDexp.exists_checked("A.TXT")
ok, size = microSDexp.file_size_checked("A.TXT")
ok, isdir = microSDexp.is_directory_checked("DIR")
```

`ok` is `False` on I²C/card/path error; inspect `last_error` then. `last_ok` is
a shorthand for `last_error == MicroSDExpError.OK`. The original methods are
unchanged and remain convenient when a failed query can simply mean "no".

## Diagnostics

`diagnostics()` returns a one-page report for troubleshooting:

```python
microSDexp.begin()
print(microSDexp.diagnostics())
```

```text
I2C microSD Expansion
---------------------
Module detected:   yes
Firmware version:  18.8.23
Protocol version:  2
SD card detected:  yes
Filesystem:        FAT32
Capacity:          3810.0 MiB / 3.72 GiB
Free space:        3801.9 MiB / 3.71 GiB
I2C address:       0x6E
I2C speed:         400 kHz (configured)
Communication:     OK
```

It is safe to call before `begin()`; unreadable fields show as `n/a`. The call
does not change `last_error`.

## Non-blocking API

If your application cannot block, the submit/poll API performs no sleeps:

```python
from i2c_microsd_module import I2CmicroSD, AsyncOp, ASYNC_BUSY, ASYNC_OK

i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
microSDexp = I2CmicroSD(i2c, address=0x6E, scl_hz=400000)
microSDexp.begin()

op = AsyncOp()
microSDexp.begin_open_write("ASYNC.TXT", op)
while microSDexp.poll_op(op) == ASYNC_BUSY:
    pass                      # do other work here

sent = 0
while sent < len(data):
    sent += microSDexp.write_now(data[sent:])  # 0 = try again next pass

target = microSDexp.committed_bytes()
while microSDexp.committed_bytes() < target:
    pass

op = AsyncOp()
microSDexp.begin_close(op)
while microSDexp.poll_op(op) == ASYNC_BUSY:
    pass
```

`begin_open_write`, `begin_open_read`, `begin_close`, `begin_format` and
`begin_query` submit a command and return immediately. `poll_op()` performs one
STATUS read (`ASYNC_BUSY`, `ASYNC_OK`, or a module error code). `write_now()`
and `read_now()` move only what fits right now — zero/empty means "try again",
not failure. `committed_bytes()` reports the commit counter. Only one async
operation may be pending at a time.

No compile-time flag is needed (unlike the Arduino port); the blocking methods
remain available and unchanged. See `nonblocking_write.py`.

## Documentation

Full API documentation is available at https://i2c-microsd-expansion-circuitpython.readthedocs.io/ and can be built locally with `Sphinx <https://www.sphinx-doc.org/>`_ from `docs/`.

---

## License

MIT. See [LICENSE](LICENSE). Not affiliated with the SD Association.
