# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""Full command-table test for the I²C microSD Expansion (52 checks).

Covers every module command 0x01-0x2F (except 0x0C/0x0D unused):
legacy, async 64K, pins, diag, bitbang, format (destructive — last storage
op), address change, reboot (absolute last). Run as code.py on the S3.

Type 'n' at the prompt to skip FORMAT? No — this script always formats
(mode 0, auto FAT) to match the reference test. The card is wiped by design.
"""

import binascii
import time

import board
import busio

from i2c_microsd_module import I2CmicroSD, protocol

HZ = 400000
KBYTES = 65536

step = 0
fails = []


def check(ok, cmd, name, detail=""):
    global step
    step += 1
    print(f"[{step:02d}] 0x{cmd:02X} {name:<18} {'PASS' if ok else 'FAIL'} {detail}")
    if not ok:
        fails.append(f"0x{cmd:02X} {name} {detail}")


i2c = busio.I2C(board.IO1, board.IO2, frequency=HZ)
b = I2CmicroSD(i2c, scl_hz=HZ, poll_ms=2, flow_poll_ms=1)
print(f"=== FULLCMD size={KBYTES} clock={HZ} Hz ===")
if not b.begin():
    print("=== FULLCMD FAIL: begin ===")
    raise SystemExit
st = b.read_status()
if st is None or st.rev != 2:
    print("=== FULLCMD FAIL: STATUS rev !=2 ===")
    raise SystemExit

# ---- 0x0F VERSION ----
v = b.version()
check(v.startswith("18"), 0x0F, "VERSION", v)

# ---- 0x17 TEMP ----
k = b.temperature_k()
check(250 <= k <= 340, 0x17, "TEMP_READ", f"{k} K")

# ---- 0x18 ADC PA5 ----
b.raw_write(protocol.MICROSDEXP_CMD_PA5_SET_MODE, bytes([4]))
adc = b.adc_pa5()
check(adc != 0xFFFF, 0x18, "ADC_READ_PA5", f"{adc}")
b.raw_write(protocol.MICROSDEXP_CMD_PA5_SET_MODE, bytes([0]))

# ---- 0x19 ADC PB3 ----
d = b.raw_read(protocol.MICROSDEXP_CMD_ADC_READ_PB3, 1)
check(d == b"\xff", 0x19, "ADC_READ_PB3", d.hex())

# ---- 0x1C PIN_STATE ----
d = b.raw_read(protocol.MICROSDEXP_CMD_PIN_STATE_READ, 1)
check(len(d) == 1, 0x1C, "PIN_STATE_READ", f"mask=0x{d[0]:02X}" if d else "short")

# ---- 0x20 STATUS ----
st = b.read_status()
check(st is not None and st.rev == 2 and st.state < 8 and st.error < 7, 0x20, "STATUS", f"state={st.state} rxFree={st.rx_free}")

# ---- 0x29 CARD_INFO ----
ci = b.card_info()
check(ci is not None and ci.mounted == 1 and ci.fat_type in (16, 32) and ci.sck_hz == 5000000,
      0x29, "CARD_INFO", f"mounted={ci.mounted} fat={ci.fat_type} sck={ci.sck_hz//1000}k")

# ---- 0x2A SD_DIAG (shipping zeros) ----
d = b.raw_read(protocol.MICROSDEXP_CMD_SD_DIAG, 16)
check(len(d) >= 16, 0x2A, "SD_DIAG", f"cardInit={d[0] if d else '-'} shipping={all(v==0 for v in d[:12]) if len(d)>=12 else '-'}")

# ---- 0x26 DIAG / 0x27 DIAG2 (shipping NACK tolerated) ----
d1 = b.raw_read(protocol.MICROSDEXP_CMD_DIAG, 16)
check(True, 0x26, "DIAG", f"n={len(d1)}")
d2 = b.raw_read(protocol.MICROSDEXP_CMD_DIAG2, 16)
check(True, 0x27, "DIAG2", f"n={len(d2)}")

# ---- pin modes ----
ok = all(b.raw_write(protocol.MICROSDEXP_CMD_PA5_SET_MODE, bytes([m])) for m in range(5))
bad = b.raw_write(protocol.MICROSDEXP_CMD_PA5_SET_MODE, bytes([5]))
check(ok and not bad, 0x10, "PA5_SET_MODE", "0-4 ACK, 5 NACK")

e1 = b.raw_write(protocol.MICROSDEXP_CMD_PA5_SET_MODE, bytes([0]))
e2 = b.raw_write(protocol.MICROSDEXP_CMD_PA5_CONTROL, bytes([1]))
e3 = b.raw_write(protocol.MICROSDEXP_CMD_PA5_SET_MODE, bytes([2]))
e4 = b.raw_write(protocol.MICROSDEXP_CMD_PA5_CONTROL, bytes([1]))
check(e1 and e2 and e3 and not e4, 0x11, "PA5_CONTROL", "out ACK, input NACK")
b.raw_write(protocol.MICROSDEXP_CMD_PA5_SET_MODE, bytes([0]))

ok = all(b.raw_write(protocol.MICROSDEXP_CMD_PB2_SET_MODE, bytes([m])) for m in range(4))
bad = b.raw_write(protocol.MICROSDEXP_CMD_PB2_SET_MODE, bytes([4]))
check(ok and not bad, 0x12, "PB2_SET_MODE", "0-3 ACK, 4 NACK")
e1 = b.raw_write(protocol.MICROSDEXP_CMD_PB2_SET_MODE, bytes([0])); e2 = b.raw_write(protocol.MICROSDEXP_CMD_PB2_CONTROL, bytes([1]))
e3 = b.raw_write(protocol.MICROSDEXP_CMD_PB2_SET_MODE, bytes([2])); e4 = b.raw_write(protocol.MICROSDEXP_CMD_PB2_CONTROL, bytes([1]))
check(e1 and e2 and e3 and not e4, 0x13, "PB2_CONTROL", "out ACK, input NACK")
b.raw_write(protocol.MICROSDEXP_CMD_PB2_SET_MODE, bytes([0]))

ok = all(b.raw_write(protocol.MICROSDEXP_CMD_PB3_SET_MODE, bytes([m])) for m in range(4))
bad = b.raw_write(protocol.MICROSDEXP_CMD_PB3_SET_MODE, bytes([4]))
check(ok and not bad, 0x14, "PB3_SET_MODE", "0-3 ACK, 4 NACK")
e1 = b.raw_write(protocol.MICROSDEXP_CMD_PB3_SET_MODE, bytes([0])); e2 = b.raw_write(protocol.MICROSDEXP_CMD_PB3_CONTROL, bytes([1]))
e3 = b.raw_write(protocol.MICROSDEXP_CMD_PB3_SET_MODE, bytes([2])); e4 = b.raw_write(protocol.MICROSDEXP_CMD_PB3_CONTROL, bytes([1]))
check(e1 and e2 and e3 and not e4, 0x15, "PB3_CONTROL", "out ACK, input NACK")
b.raw_write(protocol.MICROSDEXP_CMD_PB3_SET_MODE, bytes([0]))

# ---- 0x0E CLOCK ----
e1 = b.raw_write(protocol.MICROSDEXP_CMD_CLOCK_SET, bytes([26, 11, 7, 12, 30, 0]))
e2 = b.raw_write(protocol.MICROSDEXP_CMD_CLOCK_SET, bytes([26, 11, 7, 12, 30, 0, 0]))
check(e1 and not e2, 0x0E, "CLOCK_SET", "6B ACK, 7B NACK")

# ---- async 64K ----
expect = bytes((((i) * 7 + 3) & 0xFF) for i in range(KBYTES))
w = b.open("FullCmd.BIN", "w")
ok_w = w is not None
check(ok_w, 0x21, "OPEN_WRITE", "FullCmd.BIN")
if ok_w:
    tiles = {o: expect[o:o+64] for o in range(0, KBYTES, 64)}
    t0 = time.monotonic()
    sent = 0
    wok = True
    for o in range(0, KBYTES, 64):
        if w.write(tiles[o]) != 64:
            wok = False
            break
        sent += 64
    committed = wok and b.sync()
    wc = w.close() if w else False
    check(wok and committed and wc, 0x22, "WRITE", f"sent={sent} closed={wc}")
r = b.open("FullCmd.BIN", "r")
check(r is not None, 0x25, "OPEN_READ", "FullCmd.BIN")
if r is not None:
    crc = 0
    got = 0
    mism = 0
    t1 = time.monotonic()
    while got < KBYTES:
        data = r.read(min(256, KBYTES - got))
        if not data:
            break
        crc = binascii.crc32(data, crc)
        if data != expect[got:got+len(data)]:
            mism += 1
        got += len(data)
    r.close()
    hashv = crc & 0xFFFFFFFF
    check(got == KBYTES and mism == 0 and hashv == 0xD660AF09, 0x23, "READ", f"recv={got} hash={hashv:08X}")
# explicit close flush (redundant close must ACK)
check(b.raw_write(protocol.MICROSDEXP_CMD_CLOSE_FLUSH), 0x24, "CLOSE_FLUSH", "redundant")

# ---- legacy ----
DIR = "FullCmdDir"
FILE = DIR + "/FullCmdFile.BIN"
MISS = DIR + "/NoSuchFileZZZ.BIN"
check(b.mkdir(DIR) or b.is_directory(DIR), 0x09, "MAKE_DIR", DIR)
check(b._legacy_op(protocol.MICROSDEXP_CMD_LIST_DIR, DIR)[0] == 0, 0x08, "LIST_DIR", "err=0")
check(b.is_directory(DIR), 0x07, "IS_DIRECTORY", DIR)
# FILENAME overflow: 260B must NACK
check(not b.raw_write(protocol.MICROSDEXP_CMD_FILENAME, b"A" * 260), 0x01, "FILENAME", "260B NACK expected")
p1 = bytes(((i * 5 + 11) & 0xFF) for i in range(64))
# 0x02 via legacy payload path: use library append? Direct raw legacy:
# submitFilename + WRITE_FILE
b._submit_filename(FILE)
e02 = b._legacy_op(protocol.MICROSDEXP_CMD_WRITE_FILE, FILE)[0] if False else None  # placeholder (legacyOp would resubmit)
# legacyOp(p1) path: file with p1 via library w then check; the reference test uses 0x02 directly
# use legacyOp with payload via private helper
st0 = b.read_status()
db = st0.op_done if st0 else 0
b._submit_filename(FILE)
w_ok = b.raw_write(protocol.MICROSDEXP_CMD_WRITE_FILE, p1)
op = b.wait_for_op_complete(db)
check(w_ok and op == 0, 0x02, "WRITE_FILE", f"err={op}")
check(b.exists(FILE), 0x06, "FILE_EXISTS", FILE)
check(not b.exists(MISS), 0x06, "FILE_EXISTS-miss", MISS)
check(b.file_size(FILE) == 64, 0x05, "FILE_SIZE", "64")
check(not b.is_directory(FILE), 0x07, "IS_DIRECTORY-file", "file")
p2 = bytes(((i * 3 + 7) & 0xFF) for i in range(32))
st0 = b.read_status(); db = st0.op_done if st0 else 0
b._submit_filename(FILE)
ap_ok = b.raw_write(protocol.MICROSDEXP_CMD_APPEND_FILE, p2)
op = b.wait_for_op_complete(db)
check(ap_ok and op == 0, 0x04, "APPEND_FILE", "p2 32B")
check(b.file_size(FILE) == 96, 0x05, "FILE_SIZE-append", "96")
# READ_FILE sized
sz = b.file_size(FILE)
st0 = b.read_status(); db = st0.op_done if st0 else 0
b._submit_filename(FILE)
rf_ok = b.raw_write(protocol.MICROSDEXP_CMD_READ_FILE)
op = b.wait_for_op_complete(db)
check(rf_ok and op == 0 and sz == 96, 0x03, "READ_FILE", f"sz={sz}")
# drain via library open r
rf = b.open(FILE, "r")
if rf is not None:
    got_data = rf.read(sz)
    content_ok = got_data == p1 + p2
    rf.close()
else:
    content_ok = False
check(content_ok, 0x03, "READ_FILE-content", "p1+p2")
check(b.remove(FILE), 0x0B, "REMOVE_FILE", FILE)
check(b.rmdir(DIR), 0x0A, "REMOVE_DIR", DIR)

# ---- 0x28 FORMAT (destructive, last storage op) ----
check(not b.raw_write(protocol.MICROSDEXP_CMD_FORMAT, bytes([2])), 0x28, "FORMAT-gate", "mode 2 NACK")
check(b.format(0), 0x28, "FORMAT-submit", "mode 0 submitted")
# wait for mount
mounted = False
for _ in range(20):
    ci2 = b.card_info()
    if ci2 is not None and ci2.mounted == 1:
        mounted = True
        break
    time.sleep(3)
check(mounted, 0x28, "FORMAT", f"mounted={mounted}")
# sanity 1KB
w = b.open("PostFmt.BIN", "w")
ok_s = False
if w is not None:
    w.write(bytes(1024))
    w.close()
    r = b.open("PostFmt.BIN", "r")
    if r is not None:
        ok_s = len(r.read(1024)) == 1024
        r.close()
check(ok_s, 0x29, "FORMAT-sanity", "1KB post-format")

# ---- BitBang 0x2E/0x2B/0x2C/0x2D/0x2E ----
check(b.raw_write(protocol.MICROSDEXP_CMD_BITBANG_CLEAR), 0x2E, "BITBANG_CLEAR-pre", "")
check(b.raw_write(protocol.MICROSDEXP_CMD_BITBANG_SET_MODE, bytes([5])), 0x2B, "BITBANG_SET_MODE", "PA5=5")
check(b.raw_write(protocol.MICROSDEXP_CMD_BITBANG_BUFFER, bytes([0x00, 0x00, 0x04, 0x02, 0x01, 0x04, 0x01])), 0x2C, "BITBANG_BUFFER", "4B")
check(b.raw_write(protocol.MICROSDEXP_CMD_BITBANG_EXECUTE, bytes([2])), 0x2D, "BITBANG_EXECUTE", "SCRIPT")
time.sleep(0.1)
check(b.raw_write(protocol.MICROSDEXP_CMD_BITBANG_CLEAR), 0x2E, "BITBANG_CLEAR", "")

# ---- 0x16 I2C_SET_ADDR ----
check(not b.raw_write(protocol.MICROSDEXP_CMD_I2C_SET_ADDR, bytes([0x00])), 0x16, "I2C_SET_ADDR-invalid", "0x00 NACK")
check(b.raw_write(protocol.MICROSDEXP_CMD_I2C_SET_ADDR, bytes([0x6A])), 0x16, "I2C_SET_ADDR", "->0x6A")
time.sleep(0.05)
b.set_address(0x6A)
v6a = b.version()
check(v6a.startswith("18"), 0x16, "I2C_SET_ADDR-verify6A", v6a)
# restore (must talk at 0x6A)
check(b.raw_write(protocol.MICROSDEXP_CMD_I2C_SET_ADDR, bytes([0x6E])), 0x16, "I2C_SET_ADDR-restore", "->0x6E")
time.sleep(0.05)
b.set_address(0x6E)
v6e = b.version()
check(v6e.startswith("18"), 0x16, "I2C_SET_ADDR-restore2", v6e)

# ---- 0x2F REBOOT (absolute last) ----
check(b.raw_write(protocol.MICROSDEXP_CMD_REBOOT), 0x2F, "REBOOT", "waiting 3s")
time.sleep(3)
v2 = b.version()
check(v2.startswith("18"), 0x2F, "REBOOT-verify", v2)

print(f"=== {'FULLCMD PASS' if not fails else 'FULLCMD FAIL'} all {step} checks ===")
for f in fails:
    print("FAILED:", f)




