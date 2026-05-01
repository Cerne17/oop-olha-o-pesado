# Skill: Debug serial monitor issues

## Objective
Diagnose and fix problems with the serial monitor: garbage output, no output,
and permission errors on Linux.

## Symptoms this skill covers

| Symptom | Likely cause |
|---------|--------------|
| Garbage / scrambled characters in the monitor | Wrong baud rate |
| `Permission denied: /dev/ttyUSB0` | User not in `dialout` group |
| Monitor opens but prints nothing | Board is not running firmware (in bootloader) |
| Monitor exits immediately | Another process holds the port |

---

## Step 1 -- Check the baud rate

Both firmware images always use **115200 baud**.

Open the monitor with the correct rate:
```bash
pio device monitor --baud 115200
```

Or, from within the `robot/` or `cam/` directory, PlatformIO reads
`monitor_speed` from `platformio.ini` automatically:
```bash
cd robot   # or cam
pio device monitor
```

`platformio.ini` for both boards contains:
```ini
monitor_speed = 115200
```

If you see random symbols at any baud rate other than 115200, that confirms the
mismatch. Set 115200 and retry.

---

## Step 2 -- Linux: add user to `dialout` group

Serial port access on Linux requires membership in the `dialout` group.

```bash
sudo usermod -a -G dialout $USER
```

**You must log out and log back in** (or reboot) for the group change to take
effect. Verify:
```bash
groups $USER   # should list dialout
```

Then retry:
```bash
pio device monitor --baud 115200
```

---

## Step 3 -- Check that the board is running firmware

If the monitor shows nothing, the board may be stuck in bootloader mode.

For the Robot ESP32:
- Press the **EN** (reset) button while not holding BOOT.
- Expected output within 2 seconds:
  ```
  === Robot ESP32 booting ===
  === Ready ===
  ```

For the ESP32-CAM:
- Remove the GPIO0--GND jumper if it is still connected.
- Press **RST** or power-cycle.
- Expected output:
  ```
  === CAM ESP32 booting ===
  [CAM] Bluetooth started as 'RobotCAM'
  === Ready ===
  ```

If `FATAL: camera init failed -- halting` appears, see
[debug_cam_init.md](debug_cam_init.md).

---

## Step 4 -- Release the port from another process

If the monitor fails with `port is already in use` or opens but immediately
closes:

**macOS/Linux -- find the process holding the port:**
```bash
lsof /dev/cu.usbserial-0001    # macOS, substitute actual device
lsof /dev/ttyUSB0              # Linux
```

Kill the process by PID:
```bash
kill <PID>
```

Common culprits: a previous `pio device monitor` left running in another
terminal, or an IDE serial monitor.

---

## Reference: expected boot output

| Board | Expected serial output |
|-------|------------------------|
| Robot ESP32 | `=== Robot ESP32 booting ===` ... `=== Ready ===` |
| ESP32-CAM | `=== CAM ESP32 booting ===` ... `[CAM] Bluetooth started as 'RobotCAM'` ... `=== Ready ===` |

After `=== Ready ===`, the board is running and Bluetooth is advertising.
