# Changelog

All notable changes to the CircuitPython host library are documented here.

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
