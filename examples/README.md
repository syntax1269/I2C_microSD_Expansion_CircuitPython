# Examples

Each file is a standalone CircuitPython program. Copy one to `CIRCUITPY` as
`code.py` (and reset the board to run it).

| Example | Shows |
|---|---|
| `basic_readwrite.py` | 64 KB round trip with CRC32 verification |
| `append_and_list.py` | Append writes, directory listing, queries |
| `simpletest.py` | Probe, version, card info, temperature |
| `neopixel_blit.py` | WS2812B strip via the bit-bang engine |
| `bitbang_script.py` | Token scripts for timed pin edges |
| `sweep.py` | Throughput at 100 kHz / 400 kHz / 1 MHz |
| `exhaustive.py` | Full command-table test (destructive to the card) |
| `abrupt_recovery.py` | Recover from a mid-write power loss |

Edit the I²C pin selection near the top of an example to match your board; the
comments list common choices (board.SCL/SDA, ESP32-S3 IO1/IO2, RP2040 GP1/GP0).
