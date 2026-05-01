# Skill: Debug Bluetooth pairing and connection failures

## Objective
Diagnose and fix Bluetooth Classic SPP pairing and connection issues for both
the Robot ESP32 (`RobotESP32`) and the ESP32-CAM (`RobotCAM`).

## Symptoms this skill covers

| Symptom | Likely cause |
|---------|--------------|
| Device does not appear in Bluetooth scan | Firmware not running / board not powered |
| `/dev/cu.RobotESP32-SerialPort` not visible (macOS) | SPP profile not active -- firmware must be running before pairing |
| `Permission denied` on `/dev/rfcomm0` (Linux) | `rfcomm bind` not run or `dialout` group missing |
| Computer prints `connecting...` and never proceeds | Wrong port string in `PHASE_CONFIGS` |
| Connection drops repeatedly | Bluetooth interference or device too far from host |

---

## Step 1 -- Confirm the board is running firmware

The Bluetooth SPP profile only advertises while the firmware is running.

1. Open the serial monitor:
   ```bash
   cd robot   # or cam
   pio device monitor --baud 115200
   ```
2. Press **EN** (reset) on the board.
3. Wait for:
   ```
   === Robot ESP32 booting ===
   === Ready ===
   ```
   (or the CAM equivalent)

Only proceed to pairing after `=== Ready ===` appears.

---

## Step 2 -- Pair the device

### macOS

1. System Settings → Bluetooth.
2. Wait for `RobotESP32` (or `RobotCAM`) to appear in the device list.
3. Click **Connect**.
4. After pairing, the serial port appears:
   - `/dev/cu.RobotESP32-SerialPort`
   - `/dev/cu.RobotCAM-SerialPort`

Verify the port exists:
```bash
ls /dev/cu.Robot*
```

### Linux

```bash
bluetoothctl
> scan on
# wait for the MAC address to appear in the output, then:
> pair   AA:BB:CC:DD:EE:FF
> trust  AA:BB:CC:DD:EE:FF
> quit
```

Bind the device to a serial port (run once per session):
```bash
sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF   # robot  -> /dev/rfcomm0
sudo rfcomm bind 1 AA:BB:CC:DD:EE:FF   # cam    -> /dev/rfcomm1
```

To make the binding persistent across reboots, add the commands to
`/etc/rc.local` or a systemd service.

Also ensure your user is in the `dialout` group (see
[debug_serial.md](debug_serial.md) Step 2).

---

## Step 3 -- Update port strings in `computer/main.py`

File: `computer/main.py`, `PHASE_CONFIGS` dict.

```python
2: PhaseConfig(
    robot_port      = "/dev/cu.RobotESP32-SerialPort",   # macOS
    # robot_port    = "/dev/rfcomm0",                    # Linux
    robot_transport = "serial",
    ...
),
3: PhaseConfig(
    robot_port      = "/dev/cu.RobotESP32-SerialPort",
    cam_port        = "/dev/cu.RobotCAM-SerialPort",
    robot_transport = "serial",
    cam_transport   = "serial",
    ...
),
```

Verify the port string exactly matches what `ls /dev/cu.Robot*` shows.

---

## Step 4 -- Re-pair if the port disappears (macOS)

On macOS, the `/dev/cu.*` entry disappears if:
- The board is powered off.
- The board reboots and SPP re-advertises.

To re-establish without re-pairing:
1. Ensure the board shows `=== Ready ===` in the serial monitor.
2. In System Settings → Bluetooth, click the `i` icon next to the device name
   and choose **Connect**.
3. The `/dev/cu.*` entry should reappear within a few seconds.

---

## Step 5 -- Confirm the BT device name in firmware

The Bluetooth name must match what macOS/Linux shows in the device list.

| Board | Default BT name | Source file |
|-------|-----------------|-------------|
| Robot ESP32 | `RobotESP32` | `robot/src/main.cpp` constant `BT_NAME` |
| ESP32-CAM | `RobotCAM` | `cam/src/main.cpp` constant `BT_NAME` |

If you renamed the device in firmware but macOS still shows the old name:
- Remove the old pairing in System Settings → Bluetooth → device `i` → Forget.
- Re-pair from Step 2.

---

## Step 6 -- ESP32 board must support Bluetooth Classic

The firmware uses **Bluetooth Classic SPP**. The following ESP32 variants do
**not** support Bluetooth Classic and will not work:

- ESP32-S2
- ESP32-C3

Use a standard **ESP32** (dual-mode) devkit. The AI Thinker ESP32-CAM module
also uses a standard ESP32 chip and is supported.
