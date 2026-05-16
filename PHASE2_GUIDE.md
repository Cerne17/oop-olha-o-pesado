# Phase 2 — Manual Control over Bluetooth

This guide assumes the robot firmware is already flashed and the ESP32 is powered on.
You do not need the emulator; this phase talks to the physical robot over Bluetooth.

---

## 1. Confirm the robot is ready

Open a serial monitor (USB still connected):

```bash
cd robot
pio device monitor --baud 115200
```

Expected output:

```
=== Robot ESP32 booting ===
=== Ready ===
```

If you see garbage characters the baud rate is wrong — the firmware always uses 115200.
Once confirmed, you can unplug USB; power the robot from its battery.

---

## 2. Pair the Bluetooth device

The robot advertises itself as **`RobotESP32`** over Bluetooth Classic SPP.
Pair it once — the OS remembers it for future sessions.

### macOS

1. System Settings → Bluetooth.
2. Wait for `RobotESP32` to appear and click **Connect**.
3. After pairing, a virtual serial port appears:

```bash
ls /dev/cu.RobotESP32*
# → /dev/cu.RobotESP32-SerialPort
```

### Linux

```bash
bluetoothctl
> scan on
# wait for the MAC address to appear, e.g. AA:BB:CC:DD:EE:FF
> pair   AA:BB:CC:DD:EE:FF
> trust  AA:BB:CC:DD:EE:FF
> quit

# Bind the device to a serial port (repeat each session, or add to /etc/rc.local)
sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF
# → /dev/rfcomm0
```

---

## 3. Configure the serial port (first time only)

Open `computer/main.py` and check `PHASE_CONFIGS[2]`:

```python
2: PhaseConfig(
    robot_port = "/dev/cu.RobotESP32 ",  # macOS — default, usually correct
    # robot_port = "/dev/rfcomm0",                 # Linux — uncomment if on Linux
    cam_port   = None,
),
```

Change `robot_port` only if your OS assigned a different device path.

---

## 4. Set up the Python environment (first time only)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## 5. Run Phase 2

Make sure the robot is powered on and paired, then from the repo root:

```bash
bash scripts/run.sh 2
```

Or without the helper script:

```bash
source .venv/bin/activate
python -m computer.main --phase 2
```

Expected terminal output:

```
[run] Virtual environment activated
[run] Starting phase 2: manual control / physical robot over Bluetooth
[run] Make sure the robot ESP32 is paired and powered on before continuing.
[MAIN] Phase 2 -- manual / physical robot BT
[PHASE 2] Running -- arrow keys to move, ESC or Ctrl+C to stop
```

---

## 6. Controlling the robot

The computer reads arrow keys and sends `CONTROL_REF` frames to the robot at 20 Hz.

| Key | Action |
|-----|--------|
| `↑` | Forward |
| `↓` | Backward |
| `←` | Turn left |
| `→` | Turn right |
| `↑` + `→` | Forward-right diagonal |
| `↑` + `←` | Forward-left diagonal |
| No key held | Stop (sends zero speed) |
| `ESC` or `Ctrl+C` | Quit |

Diagonal combinations work — the controller computes the heading angle from
simultaneous key presses and maps it to left/right wheel power.

The robot's rate limiter ramps power at 0.02 per tick at 50 Hz, so it takes
about one second to reach full speed from rest. This is by design.

---

## 7. What to watch for

- **Wheels don't move** — heartbeat frames are still sent; if the robot receives
  them but wheels stay still, check the H-bridge wiring and motor power supply.
- **Left/right swapped** — swap `LEFT_WHEEL` and `RIGHT_WHEEL` pin assignments
  in `robot/src/main.cpp` and re-flash.
- **Robot stops after ~5 s without input** — normal. The watchdog on the ESP32
  cuts motor power if no `CONTROL_REF` or heartbeat arrives for 5 seconds.
  This is a safety feature — keep the computer running while driving.

---

## 8. Stopping

Press **ESC** or **Ctrl+C**. The computer sends a final stop signal before exiting.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `[Errno 2] No such file or directory: '/dev/cu.RobotESP32-SerialPort'` | Device not paired or ESP32 not running | Confirm `=== Ready ===` in serial monitor, then re-pair |
| `[Errno 16] Resource busy` | Another process has the port open | Close any other serial monitor or terminal connected to the device |
| Port not visible after pairing (macOS) | SPP profile not active | The ESP32 must be running firmware before the port appears — power it on, wait for `=== Ready ===`, then pair |
| `Permission denied: /dev/rfcomm0` (Linux) | User not in `dialout` group | `sudo usermod -a -G dialout $USER` then log out and back in |
| Robot connects but doesn't move | Motor power supply missing | H-bridge needs its own power supply; ESP32 3.3 V alone cannot drive motors |
| Arrow keys have no effect | Terminal focus issue | Click the terminal window running the computer — `pynput` reads from the focused window |
