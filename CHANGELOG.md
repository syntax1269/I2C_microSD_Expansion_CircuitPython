# Changelog

All notable changes to the CircuitPython host library are documented here.

## [1.0.9] - 2026-11-20

### Added

- Four new examples: `sensor_ring_logger.py` (500 Hz sampling into a 512-byte
  ring, drained with `write_now()` / `committed_bytes()`),
  `config_save_load.py` (checked queries plus a staged settings update),
  `dual_module_mirror.py` (two modules on one bus with `sticky_error`
  failover) and `threshold_bitbang_alert.py` (CSV logging plus a module-side
  strobe script).

## [1.0.8] - 2026-11-19

### Added

- **Checked query variants**: `exists_checked`, `file_size_checked` and
  `is_directory_checked` return `(ok, value)` so "not found" is distinct from
  a failed I²C transaction. Added `last_ok` shorthand. Original methods
  unchanged.

## [1.0.7] - 2026-11-19

### Added

- **Non-blocking submit/poll API**: `begin_open_write`, `begin_open_read`,
  `begin_close`, `begin_format`, `begin_query`, `poll_op`, `write_now`,
  `read_now`, `committed_bytes`, plus the `AsyncOp` token and `ASYNC_*` result
  constants. No sleeps; one STATUS read per poll; only one pending operation.
  No feature flag needed; the blocking API is unchanged.
- Example `nonblocking_write.py` and updated README/RTD documentation.

## [1.0.6] - 2026-11-19

### Changed

- Documented blocking behavior and worst-case timeouts for every high-level
  method in README and RTD docs. The Python ports remain synchronous; use a
  worker thread/task if your application cannot block.

## [1.0.5] - 2026-11-19

### Added

- **`diagnostics()`** returns a one-page health report (module, firmware and
  protocol version, card/filesystem, capacity and free space, I²C address and
  configured clock, communication verdict) for customer troubleshooting. Safe
  before `begin()` (`n/a` for unreadable fields) and leaves `last_error`
  unchanged. Uses the module's real `free_clusters` value.
- `examples/diagnostics.py` and an API entry for the new method.

## [1.0.4] - 2026-11-19

### Added

- **Sticky error API.** `sticky_error` reports the first failure since
  `clear_error()`; `last_error` keeps its per-call semantics. Internal calls can
  no longer hide a real fault from a caller that checks the sticky value.
- **Version parse signal.** `version()` now sets `INVALID` when no dotted token
  can be parsed from the answered banner.

## [1.0.3] - 2026-11-18

### Fixed

- **Consistent sensor error sentinel.** `temperature_k()` and `adc_pa5()` now
  both return `0xFFFF` on any failure (bus error or short read), matching the
  Arduino port. `adc_pa5()` previously returned `0` on bus failures, which is a
  valid ADC reading.

## [1.0.2] - 2026-11-18

### Fixed

- **`bitbang_buffer()` workspace bounds.** The old guard rejected only
  `offset + count > 0xFFFF`, so writes between 256 and 65535 were sent to the
  module and silently dropped or NACKed instead of failing at the host. It now
  rejects any range outside the 256-byte workspace
  (`protocol.BITBANG_WORKSPACE_SIZE`), including negative offsets, with
  `MicroSDExpError.INVALID`.

## [1.0.1] - 2026-11-18

### Fixed

- **`version()` against firmware ≥ 18.8.** CMD `0x0F` answers with a 112-byte
  banner whose first line is the measured clock. `version()` now scans the banner
  for a dotted version token (`18.8.22` verified) and falls back to the legacy
  short answer. Added `firmware_banner()` and `firmware_clock_hz()`.
- **`format()` timing.** Now waits on a dedicated 300 s budget instead of the
  15 s operation timeout.

### Changed

- Standardized identifiers across the three host ports (`MICROSDEXP_*`,
  `MicroSDExpError`, `MicroSDExpFile`, `microSDexp`).

## [1.0.0] - 2026-11-16

### Added

- Expansion-pin and bit-bang API (`set_pin_mode`, `write_pin`, `save_pin_mode`,
  `show_neopixels`, `bitbang_*`).
- Streaming file API with context-manager files and explicit commit semantics.
- 256-byte read chunk support via `set_read_chunk_bytes()`.
