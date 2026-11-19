# CircuitPython Library Wiki

Technical documentation for the **I²C microSD Expansion CircuitPython library**.
The [README](../README.md) teaches you how to use the library; this wiki goes
deeper, including how to talk to the module with raw I²C commands if you would
rather write your own driver.

## Where to go

| I want to… | Go to |
|---|---|
| Install / wire | [README](../README.md#install) · [Wiring guide](../docs/wiring.md) |
| Use the library | [README](../README.md#using-the-library) · [API reference](../docs/api.md) |
| Full command set | [Protocol Reference](Protocol-Reference.md) |
| Write my own I²C driver | [Direct I²C Guide](Direct-I2C-Guide.md) |
| Raw file read/write | [File Operations](File-Operations.md) |
| Completion / polling | [Status and Polling](Status-and-Polling.md) |
| PA5 / PB2 / PB3 | [Expansion Pins](Expansion-Pins.md) |
| WS2812B / scripts | [Bit-Bang Engine](Bit-Bang-Engine.md) |
| Decode an error | [Error Codes](Error-Codes.md) |

## 60-second summary

```python
import board, busio
from i2c_microsd_module import I2CmicroSD

i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
microSDexp = I2CmicroSD(i2c, address=0x6E, scl_hz=400000)
if not microSDexp.begin():
    raise SystemExit("module not found")

with microSDexp.open("HELLO.TXT", "w") as f:
    f.write(b"HELLO-WORLD")        # close() commits to the card
```

The module is an I²C peripheral at `0x6E` that owns the FAT filesystem. One
command byte plus optional payload per transaction; reads use a repeated START.
The critical rule: **an ACK is not a commit** — poll the STATUS `opDone` counter
and `result` latch before trusting a write. See
[Status and Polling](Status-and-Polling.md).

## Page index

- **[Protocol Reference](Protocol-Reference.md)** — commands, frames, streams,
  banner, paths, timeouts.
- **[Direct I²C Guide](Direct-I2C-Guide.md)** — transaction shapes and recipes.
- **[File Operations](File-Operations.md)** — raw file sequences with flow control.
- **[Status and Polling](Status-and-Polling.md)** — opDone, result, NACKs, recovery.
- **[Expansion Pins](Expansion-Pins.md)** — modes, ADC, EEPROM, address change.
- **[Bit-Bang Engine](Bit-Bang-Engine.md)** — NeoPixel frames and script tokens.
- **[Error Codes](Error-Codes.md)** — enums and troubleshooting.

## Firmware floors

| Feature | Minimum firmware |
|---|---|
| File API | 18.5.x |
| Pins + bit-bang | 18.5.2 |
| Banner frames + measured clock | 18.8.0 |

Check with `microSDexp.version()`.
