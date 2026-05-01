# Skill: Debug firmware upload failures

## Objective
Diagnose and fix failures when running `pio run --target upload` for the robot
ESP32 or the ESP32-CAM. Covers bootloader mode, esptool connectivity, and
upload speed issues.

## Symptoms this skill covers

| Error message | Likely cause |
|---------------|--------------|
| `A fatal error: Failed to connect to ESP32` | Board not in bootloader mode |
| `esptool.py: command not found` | PlatformIO not installed |
| Upload succeeds but board is unresponsive | GPIO0 still tied to GND |
| `A fatal error occurred: Failed to connect` (CAM only) | GPIO0 not held during power-on |
| Upload hangs at `Connecting....` indefinitely | FTDI adapter TX/RX swapped or wrong voltage |

---

## Step 1 — Confirm PlatformIO is installed

```bash
pio --version
```

If this fails:
```bash
pip install platformio
```

Then retry the upload.

---

## Step 2 — Robot ESP32: enter bootloader mode

Most ESP32 devkits have an auto-reset circuit driven by the FTDI chip — the
upload tool toggles DTR/RTS to reset the chip into bootloader mode automatically.

If auto-reset fails:
1. Hold the **BOOT** (or **IO0**) button on the board.
2. While holding BOOT, press and release **EN** (reset).
3. Release BOOT.
4. Run `pio run --target upload` immediately.

If no buttons are present, pull GPIO0 to GND with a jumper, then power-cycle.

---

## Step 3 — ESP32-CAM: manual bootloader mode

The AI Thinker ESP32-CAM has **no auto-reset circuit**. The procedure is manual
every time.

1. Connect **GPIO0 to GND** (a short jumper wire to the adjacent GND pin).
2. Power-cycle the board: disconnect and reconnect 3.3 V, or press **RST**.
3. Run `pio run --target upload` from the `cam/` directory:
   ```bash
   cd cam
   pio run --target upload
   ```
4. Watch for `Connecting....` in the output. The moment dots start appearing,
   **remove the GPIO0--GND jumper**.
5. The upload proceeds and shows a progress bar.

After flashing completes:
- Remove the GPIO0--GND jumper (if not already done).
- Press **RST** to boot the new firmware normally.

> **Common mistake**: leaving GPIO0 tied to GND after the upload. The board
> will re-enter bootloader mode on every power-on and appear unresponsive.

---

## Step 4 — Check FTDI adapter wiring (CAM only)

The AI Thinker ESP32-CAM requires an external FTDI or USB-serial adapter.

| FTDI adapter | ESP32-CAM pin |
|-------------|---------------|
| GND         | GND           |
| VCC (3.3 V) | 3.3V          |
| TX          | U0RXD (GPIO3) |
| RX          | U0TXD (GPIO1) |

Critical points:
- Use **3.3 V logic**. The ESP32-CAM is not 5 V tolerant on GPIO.
- TX on the adapter connects to RX on the board, and vice versa.
- Some adapters have a 3.3 V / 5 V selector jumper -- ensure it is on 3.3 V.

---

## Step 5 — Reduce upload speed (CAM)

If the CAM still fails to connect after correct wiring and bootloader mode:

Add to `cam/platformio.ini` under `[env:esp32cam]`:
```ini
upload_speed = 115200
```

Then retry:
```bash
cd cam
pio run --target upload
```

---

## Step 6 — Verify the serial port is detected

**macOS:**
```bash
ls /dev/cu.usbserial* /dev/cu.SLAB_USBtoUART* 2>/dev/null
```

**Linux:**
```bash
ls /dev/ttyUSB* /dev/ttyACM*
```

If nothing appears, the USB-serial driver is missing. Install the driver that
matches the chip on your board:

| Chip | Driver source |
|------|---------------|
| CP2102 | Silicon Labs CP210x (silabs.com) |
| CH340 / CH341 | WCH CH340 (wch-ic.com) |
| FTDI | Built into macOS/Linux; Windows needs FTDI VCP |

Check which chip is on your board with `lsusb` (Linux) or System Information
(macOS) while the board is plugged in.

---

## Step 7 — Specify the port explicitly

If PlatformIO detects the wrong port or multiple ports exist:

```bash
pio run --target upload --upload-port /dev/cu.usbserial-0001
```

Substitute the actual device path from Step 6.

---

## Expected successful output

```
Writing at 0x00010000... (100 %)
Wrote XXXXXX bytes ...
Hash of data verified.
Leaving...
Hard resetting via RTS pin...
```

After this, run the serial monitor to confirm the firmware booted:
```bash
pio device monitor --baud 115200
```

Expected:
- Robot: `=== Robot ESP32 booting ===` then `=== Ready ===`
- CAM: `=== CAM ESP32 booting ===` then `=== Ready ===`
