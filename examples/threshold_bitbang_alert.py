# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""threshold_bitbang_alert — the module alone produces the timed alert.

Port of ThresholdBitbangAlert.ino. Every 500 ms the host reads adc_pa5() and
temperature_k() and appends a CSV row. When the ADC crosses THRESHOLD it loads
a 300 ms strobe script into the module's bit-bang workspace and starts it on
PB2. The module plays the pulse train itself; the host must keep the I2C bus
quiet for the script duration, then resumes logging.

Wiring: LED + resistor (or a scope probe) on PB2; a sensor on PA5 makes the
threshold meaningful. Adjust SCL/SDA for your board.
"""

import time

import board
import busio

from i2c_microsd_module import I2CmicroSD, protocol

THRESHOLD = 3000
RUN_S = 30.0
STROBE_S = 0.31  # script (300 ms) + slack

ALERT_PIN = protocol.MICROSDEXP_PIN_PB2

# 3 x (50 ms high, 50 ms low). Offsets: 0 SET_HIGH, 1 DELAY_MS(50),
# 3 SET_LOW, 4 DELAY_MS(50), 6 LOOP_GOTO(target 0, 3 passes).
STROBE = bytes(
    [
        0x01, 0x04, 50,
        0x02, 0x04, 50,
        0x05, 0x00, 3,
    ]
)

i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
microSDexp = I2CmicroSD(i2c, address=0x6E, scl_hz=400000)
if not microSDexp.begin():
    raise SystemExit("threshold_bitbang_alert: module not found")

if not microSDexp.set_pin_mode(ALERT_PIN, 0) or not microSDexp.bitbang_set_mode(ALERT_PIN):
    raise SystemExit("threshold_bitbang_alert: pin setup failed")
microSDexp.bitbang_clear()  # no stale tokens behind the strobe

f = microSDexp.open("ALERT.CSV", "w")
if f is None:
    raise SystemExit("threshold_bitbang_alert: open failed")
f.write(b"millis,adc,tempK,alert\n")
start = time.monotonic()
alerts = 0


def play_strobe():
    """Buffer and start the script, then wait it out with NO I2C traffic."""
    if not microSDexp.bitbang_buffer(0, STROBE):
        return False
    if not microSDexp.bitbang_execute(protocol.MICROSDEXP_BITBANG_PROFILE_SCRIPT):
        return False
    time.sleep(STROBE_S)  # the module is playing: keep the bus quiet
    return True


while time.monotonic() - start < RUN_S:
    adc = microSDexp.adc_pa5()
    temp_k = microSDexp.temperature_k()
    alert = adc != 0xFFFF and adc >= THRESHOLD
    now_ms = int((time.monotonic() - start) * 1000)
    f.write(f"{now_ms},{adc},{temp_k},{1 if alert else 0}\n".encode("ascii"))

    if alert:
        alerts += 1
        if not play_strobe():
            print("threshold_bitbang_alert: strobe FAILED")

    time.sleep(0.5)  # ~2 Hz sample cadence when no alert is firing

f.close()
print(f"threshold_bitbang_alert: DONE alerts={alerts}")
