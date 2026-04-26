# Firmware Setup Guide

Step-by-step instructions for installing the toolchain, wiring the hardware,
building the firmware, and flashing both ESP32 boards.

---

## 1. Software requirements

### 1.1 Python

PlatformIO is distributed as a Python package. Python 3.8 or later is required.

```bash
python --version    # must be 3.8+
```

### 1.2 PlatformIO Core (CLI)

```bash
pip install platformio
pio --version       # confirm install
```

Alternatively, install the **PlatformIO IDE** extension for VS Code — it
bundles the CLI and adds build/upload/monitor buttons to the editor.

### 1.3 Espressif32 platform and toolchain

PlatformIO downloads the toolchain automatically on first build. To pre-fetch:

```bash
pio pkg install --global --platform espressif32
```

This downloads ~300 MB (GCC cross-compiler for Xtensa LX6, esptool, SDK).

### 1.4 USB-serial drivers

The ESP32 development boards use a USB-to-UART chip. The required driver
depends on the chip on your specific board.

| Chip | Common boards | Driver |
|------|---------------|--------|
| CP2102 | Many ESP32 devkits | [Silicon Labs CP210x](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers) |
| CH340 / CH341 | Cheaper clones, AI Thinker | [WCH CH340](https://www.wch-ic.com/downloads/CH341SER_EXE.html) |
| FTDI | Older boards | Built into macOS/Linux; Windows needs [FTDI VCP](https://ftdichip.com/drivers/vcp-drivers/) |

**macOS**: drivers may already be included. Check with:
```bash
ls /dev/cu.usbserial* /dev/cu.SLAB_USBtoUART* 2>/dev/null
```

**Linux**: add your user to the `dialout` group, then log out and back in:
```bash
sudo usermod -a -G dialout $USER
```
Check the device appears:
```bash
ls /dev/ttyUSB* /dev/ttyACM*
```

---

## 2. Hardware — Robot ESP32

### 2.1 Board

Any generic **ESP32 development board** (`esp32dev` in PlatformIO). The
firmware uses Bluetooth Classic SPP, which requires a dual-mode ESP32 —
**ESP32-S2 and ESP32-C3 do not support Bluetooth Classic** and will not work.

### 2.2 Wiring

The robot firmware drives two DC motors through H-bridge modules (e.g. L298N,
TB6612FNG, or DRV8833). Each H-bridge needs two control signals per side:

| Signal | Description |
|--------|-------------|
| `pwm`  | PWM signal to H-bridge EN/STBY — controls speed via duty cycle |
| `dir`  | Logic level to H-bridge IN pins — controls direction |

Default pin assignment (`robot/src/main.cpp:11-14`):

| Motor side | PWM pin | DIR pin |
|------------|---------|---------|
| Left wheel  | GPIO 14 | GPIO 12 |
| Right wheel | GPIO 15 | GPIO  2 |

To change the pins, edit `robot/src/main.cpp`:
```cpp
static constexpr WheelPins LEFT_WHEEL  = { .pwm = 14, .dir = 12 };
static constexpr WheelPins RIGHT_WHEEL = { .pwm = 15, .dir =  2 };
```

### 2.3 L298N wiring example

```
ESP32 GPIO14 ──► L298N ENA   (left motor speed)
ESP32 GPIO12 ──► L298N IN1   (left motor direction)
ESP32 GND    ──► L298N GND   (common ground — required)

ESP32 GPIO15 ──► L298N ENB   (right motor speed)
ESP32 GPIO2  ──► L298N IN3   (right motor direction)

L298N OUT1/OUT2 ──► left motor terminals
L298N OUT3/OUT4 ──► right motor terminals
L298N 12V       ──► motor power supply (separate from ESP32 3.3 V)
```

> **Important**: share a common GND between the ESP32 and the H-bridge power
> supply. Without it, the direction signals will float.

---

## 3. Hardware — ESP32-CAM

### 3.1 Board

The firmware targets the **AI Thinker ESP32-CAM** module. This is the most
common ESP32-CAM form factor and is what the pin map in
`cam/src/communication/CamComm.cpp:9-26` maps to.

The AI Thinker board has a built-in OV2640 camera and does **not** have a
USB port. You need a separate **FTDI or USB-serial adapter** (3.3 V logic) to
flash it.

### 3.2 Wiring the FTDI adapter for flashing

| FTDI adapter | ESP32-CAM |
|-------------|-----------|
| GND         | GND       |
| VCC (3.3 V) | 3.3V      |
| TX          | U0RXD (GPIO3) |
| RX          | U0TXD (GPIO1) |

> Use 3.3 V logic level. The ESP32-CAM is **not** 5 V tolerant on its GPIO.
> Some boards also work with 5 V on VCC but 3.3 V TX/RX — check your specific
> adapter.

### 3.3 GPIO0 bootloader mode

The ESP32-CAM has no automatic reset circuit. To enter flash mode:

1. Connect **GPIO0 to GND** (a jumper wire to the GND pin next to GPIO0 works).
2. Power-cycle or press the onboard **RST** button.
3. The board is now in bootloader mode — start the upload immediately.
4. When `esptool` prints `Connecting...` and shows dots, **release GPIO0** (remove the jumper).
5. The upload proceeds; the progress bar appears.

After flashing, remove the GPIO0–GND connection, then press RST to boot the
new firmware normally.

### 3.4 Camera pin map (AI Thinker, already in firmware)

These are hardcoded in `cam/src/communication/CamComm.cpp` and do not need
to be changed for the standard AI Thinker board:

| Signal | GPIO |
|--------|------|
| PWDN   | 32   |
| RESET  | —    |
| XCLK   | 0    |
| SIOD   | 26   |
| SIOC   | 27   |
| D7–D2  | 35, 34, 39, 36, 21, 19, 18, 5 |
| VSYNC  | 25   |
| HREF   | 23   |
| PCLK   | 22   |

---

## 4. Build and flash — Robot ESP32

### 4.1 Connect the board

Plug the ESP32 into USB. Confirm the serial device appears:
```bash
# macOS
ls /dev/cu.usbserial* /dev/cu.SLAB*

# Linux
ls /dev/ttyUSB* /dev/ttyACM*
```

### 4.2 Build and upload

```bash
cd robot
pio run --target upload
```

PlatformIO auto-detects the serial port. If it fails to detect or you have
multiple ports, specify it explicitly:
```bash
pio run --target upload --upload-port /dev/cu.usbserial-0001
```

Expected output:
```
...
Writing at 0x00010000... (100 %)
Wrote XXXXXX bytes ...
Hash of data verified.
Leaving...
Hard resetting via RTS pin...
```

### 4.3 Verify with the serial monitor

```bash
pio device monitor --baud 115200
```

Expected boot output:
```
=== Robot ESP32 booting ===
=== Ready ===
```

If you see garbage characters, the baud rate is wrong. The firmware always
uses 115200 (`robot/platformio.ini:monitor_speed`).

### 4.4 Build only (no upload)

```bash
pio run
```

The compiled binary is written to `robot/.pio/build/esp32/firmware.bin`.

---

## 5. Build and flash — ESP32-CAM

### 5.1 Wire the FTDI adapter

Follow section 3.2. GPIO0 must be connected to GND before powering on.

### 5.2 Enter bootloader mode

1. Connect GPIO0 to GND.
2. Power-cycle the board (disconnect and reconnect 3.3 V, or press RST).

### 5.3 Build and upload

```bash
cd cam
pio run --target upload
```

When you see `Connecting....` in the terminal output, release GPIO0 (remove
the GPIO0–GND jumper). The upload should proceed:

```
esptool.py v4.x.x
...
Connecting....
Chip is ESP32-D0WD-V3 (revision 3)
...
Writing at 0x00010000... (100 %)
Hash of data verified.
```

If the upload fails with `A fatal error occurred: Failed to connect`:
- Power-cycle the board again with GPIO0 tied to GND.
- Try a lower upload speed — add to `cam/platformio.ini`:
  ```ini
  upload_speed = 115200
  ```
- Try a different FTDI adapter or USB cable.

### 5.4 Verify with the serial monitor

Remove the GPIO0–GND jumper, then press RST or power-cycle.

```bash
pio device monitor --baud 115200
```

Expected boot output:
```
=== CAM ESP32 booting ===
[CAM] Bluetooth started as 'RobotCAM'
=== Ready ===
```

If you see `[CAM] FATAL: camera init failed — halting`, the camera ribbon
cable is loose or reversed. Reseat it and retry.

---

## 6. Configuration reference

### Robot (`robot/src/main.cpp`)

| Constant | Default | Description |
|----------|---------|-------------|
| `BT_NAME` | `"RobotESP32"` | Bluetooth device name — must match the port the computer pairs to |
| `LEFT_WHEEL.pwm` | `14` | PWM pin for left motor speed |
| `LEFT_WHEEL.dir` | `12` | Direction pin for left motor |
| `RIGHT_WHEEL.pwm` | `15` | PWM pin for right motor speed |
| `RIGHT_WHEEL.dir` | `2` | Direction pin for right motor |

### CAM (`cam/src/main.cpp`)

| Constant | Default | Description |
|----------|---------|-------------|
| `BT_NAME` | `"RobotCAM"` | Bluetooth device name |
| `TARGET_FPS` | `6.0` | Target JPEG stream frame rate |

### CAM image quality (`cam/src/communication/CamComm.cpp:328-329`)

| Setting | Default | Notes |
|---------|---------|-------|
| `frame_size` | `FRAMESIZE_QVGA` | 320×240 — change to `FRAMESIZE_VGA` for 640×480 |
| `jpeg_quality` | `15` | 0 = highest quality (largest file), 63 = lowest |

Increasing resolution or decreasing `jpeg_quality` increases JPEG size and
may saturate the Bluetooth link at 6 FPS. Reduce `TARGET_FPS` or increase
`jpeg_quality` if frames are dropped.

---

## 7. Bluetooth pairing

After the firmware is running and the serial monitor shows `=== Ready ===`:

**macOS**
1. System Settings → Bluetooth → wait for `RobotESP32` / `RobotCAM` to appear.
2. Click Connect.
3. The device appears as `/dev/cu.RobotESP32-SerialPort` (and similarly for CAM).

**Linux**
```bash
bluetoothctl
> scan on
> # wait for the MAC address to appear, then:
> pair   AA:BB:CC:DD:EE:FF
> trust  AA:BB:CC:DD:EE:FF
> quit

# Bind to a serial port (run once per session, or add to /etc/rc.local)
sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF   # robot  → /dev/rfcomm0
sudo rfcomm bind 1 AA:BB:CC:DD:EE:FF   # cam    → /dev/rfcomm1
```

After pairing, update the port strings in `computer/main.py` `PHASE_CONFIGS`:
```python
2: PhaseConfig(
    robot_port = "/dev/cu.RobotESP32-SerialPort",   # macOS
    # robot_port = "/dev/rfcomm0",                  # Linux
    ...
),
3: PhaseConfig(
    robot_port = "/dev/cu.RobotESP32-SerialPort",
    cam_port   = "/dev/cu.RobotCAM-SerialPort",
    ...
),
```

---

## 8. Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `A fatal error: Failed to connect to ESP32` | Board not in bootloader mode | Power-cycle with GPIO0 tied to GND (CAM) or hold BOOT button (robot devkit) |
| `Permission denied: /dev/ttyUSB0` | User not in `dialout` group | `sudo usermod -a -G dialout $USER` then log out |
| Serial monitor shows garbage | Wrong baud rate | Firmware always uses 115200 |
| `[CAM] FATAL: camera init failed` | Camera ribbon cable loose | Reseat the ribbon; check orientation |
| Board not detected after pairing (macOS) | SPP profile not active | Ensure ESP32 is running firmware (shows `=== Ready ===`) before pairing |
| `esptool.py: command not found` | PlatformIO not installed | `pip install platformio` |
| Upload succeeds but device is unresponsive | GPIO0 still tied to GND | Remove GPIO0–GND jumper and press RST |
