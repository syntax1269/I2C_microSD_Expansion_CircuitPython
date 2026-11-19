# API Reference

All classes are importable from `i2c_microsd_module`.

## `I2CmicroSD(i2c, address=0x6E, scl_hz=400000, poll_ms=10, flow_poll_ms=2)`

Create a module instance on a `busio.I2C` bus you own. `I2CmicroSD.from_bus(i2c,
address=0x6E, **kw)` is an equivalent builder.

| Member | Description |
|---|---|
| `begin()` | Probe the module; `True` when it answers |
| `set_address(addr)` | Point the object at another module address (no bus traffic) |
| `set_poll_interval(ms)` | STATUS poll pause while waiting (default 10 ms) |
| `set_read_chunk_bytes(n)` / `read_chunk_bytes` | Bytes per READ drain (default 128) |
| `version()` | Firmware string, e.g. `"18.8.22"` |
| `firmware_banner()` | Full CMD 0x0F answer (18.8.0+) |
| `firmware_clock_hz()` | Measured module clock, `0` on older firmware |
| `temperature_k()` | Die temperature in whole kelvin (2-byte LE); `0xFFFF` on error |
| `adc_pa5()` | Raw 12-bit ADC word, `0xFFFF` if unavailable |
| `card_info()` | `CardInfo` with mounted, FAT type, sector count, SCK Hz |
| `read_status()` | Raw 12-byte `StatusFrame` |
| `last_error` / `sticky_error` / `clear_error()` | Last result / first failure since clear / reset both |
| `file_open` | Whether a file is open |
| `valid_path(path)` | Length-gate a path without bus traffic |

### Files

| Member | Description |
|---|---|
| `open(path, mode)` | `"r"` / `"w"` / `"a"` → `MicroSDExpFile` or `None`; context manager |
| `open_read` / `open_write` / `open_append(path)` | Explicit openers |
| `write(data)` / `read(n)` | Stream bytes (also on the module for compatibility) |
| `sync()` | Wait until written bytes are committed |
| `close()` | Flush + close + wait for commit |

### Directories

`list_dir(path, max_entries=64)` → list of `DirEntry(is_dir, name, size)`;
`mkdir`, `rmdir`, `remove`, `exists`, `file_size`, `is_directory`.

### Pins and bit-bang

`set_pin_mode(pin, mode)` (`0` = output), `write_pin(pin, value)`,
`save_pin_mode()`, `bitbang_set_mode(pin)`, `bitbang_buffer(offset, data,
length=None)`, `bitbang_execute(profile)`, `bitbang_clear()`,
`show_neopixels(pin, grb, pixel_count=None)`.

### Housekeeping

`set_clock_time(y, mo, d, h, mi, s)`, `reboot()`, `format(mode=0)` (destructive,
up to 300 s).

## `CardInfo`

`mounted`, `fat_type`, `card_type`, `sector_count`, `free_clusters`,
`cluster_count`, `sck_hz`; `free_bytes` property; readable `__repr__`.

`fat_type` uses SdFat values: `0` unmounted, `12`/`16`/`32`/`64`.

## `DirEntry`

`is_dir`, `name`, `size`.

## `MicroSDExpFile`

`write(data)`, `read(n)`, `sync()`, `close()`, `microSDexp` (owner), `is_open`,
plus `__enter__` / `__exit__` for `with` statements.

## `MicroSDExpError`

`OK(0)`, `NO_MODULE(1)`, `NO_FILE(2)`, `OPEN_FAIL(3)`, `CARD_ERR(4)`,
`QUEUE_FULL(5)`, `INVALID(6)`, `OVERFLOW(7)`, `TIMEOUT(8)`.

## `protocol` and `config`

`i2c_microsd_module.protocol` mirrors the wire constants (commands, pin IDs,
bit-bang profiles, state/error values) — see the
[Protocol Reference](../wiki/Protocol-Reference.md). `config` exposes tunables
such as `OP_TIMEOUT_MS`, `COMMIT_TIMEOUT_MS`, `FORMAT_TIMEOUT_MS`, and
`BITBANG_MAX`.
