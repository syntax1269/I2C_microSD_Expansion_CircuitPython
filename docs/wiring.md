# Wiring Guide

The module needs four connections. It translates bus logic levels, so no external
level shifter is required.

## Basic connection

| Board pin | Module pin |
|---|---|
| SDA | SDA |
| SCL | SCL |
| GND | GND |
| 3.3 V **or** 5 V | Power (choose one) |

- Power from **5 V or 3.3 V, never both**. Use a short, decoupled lead — the SD
  card draws short current peaks during writes.
- The module has **3.3 kΩ pull-ups** fitted. Remove them via the underside trace
  cut if your host provides its own.
- Expansion pins PA5, PB2, PB3 are 3.3 V logic; a 5 V WS2812B strip needs a
  level shifter on DIN.

## Creating the bus

Pass the pins you wired to `busio.I2C(scl, sda, frequency=...)`. Common examples:

```python
import board, busio

# Boards that expose named SCL/SDA
i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)

# ESP32-S3 Super Mini: IO1 = SCL, IO2 = SDA
i2c = busio.I2C(board.IO1, board.IO2, frequency=400000)

# RP2040: GP1 = SCL, GP0 = SDA
i2c = busio.I2C(board.GP1, board.GP0, frequency=1000000)
```

Then create the library object with the same bus frequency:

```python
from i2c_microsd_module import I2CmicroSD
microSDexp = I2CmicroSD(i2c, address=0x6E, scl_hz=400000)
```

`scl_hz` is used for timeout scaling; keep it equal to the bus frequency.

## Raspberry Pi hosts (clock stretching)

The module uses standard I²C clock stretching (a few microseconds per byte).
Raspberry Pi hosts built on the **Broadcom BSC** peripheral
(**BCM2835–BCM2711**, Pi 1/2/3/4 and matching Compute Modules) have a **silicon
bug** that can corrupt transactions when a slave stretches the clock. Add
`dtoverlay=i2c-gpio` to `/boot/config.txt` (`/boot/firmware/config.txt` on
Bookworm) and reboot to use the bit-banged bus, or use a Pi 5, whose RP1
southbridge uses Synopsys DesignWare I²C and is unaffected. See
[Clock stretching and Raspberry Pi hosts](../wiki/Protocol-Reference.md#clock-stretching-and-raspberry-pi-hosts).

## Expansion pins

| Signal | Pin ID | Capability |
|---|---|---|
| PA5 | 5 | Digital out, PWM, 12-bit ADC |
| PB2 | 2 | Digital out, PWM |
| PB3 | 3 | Digital out (no ADC) |

Import the IDs from `i2c_microsd_module.protocol` as `MICROSDEXP_PIN_PA5`,
`MICROSDEXP_PIN_PB2`, `MICROSDEXP_PIN_PB3`.

## Before you start

Format the card as FAT16/FAT32 (not exFAT), verify the module answers at `0x6E`
with an I²C scanner, and check `version()` / `card_info()` from code before
writing anything. See [Expansion Pins](../wiki/Expansion-Pins.md) for raw pin
commands.
