# Running the Project

This document covers how to build, flash, and run every component of the system.
Read the phase you intend to test — you do not need all three components active at once.

---

## Prerequisites

### Python (computer + emulator)

```bash
python -m venv .venv
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows

pip install -e .
```

### PlatformIO (firmware)

```bash
pip install platformio
# or install the PlatformIO IDE extension for VS Code
```

---

## Phase 1 — Manual control, no hardware

Two processes on the same machine connected over a TCP loopback socket.

**Terminal 1 — robot emulator:**
```bash
python emulator/src/main.py --port 5001
```

**Terminal 2 — computer (keyboard control):**
```bash
python -m computer.main --phase 1
# or use the helper script:
bash scripts/run.sh 1
```

Arrow keys move the robot. The emulator terminal shows live wheel power and speed.
Press **Ctrl+C** in either terminal to stop. Each side reconnects automatically if the other restarts.

---

## Phase 2 — Manual control, physical robot

### 1. Flash the robot firmware

Connect the robot ESP32 via USB, then from the repo root:

```bash
cd robot
pio run --target upload
pio device monitor      # optional: watch serial output
```

### 2. Pair Bluetooth

- **macOS**: System Settings → Bluetooth → pair `RobotESP32`
- **Linux**: `bluetoothctl` → `pair <MAC>` → `trust <MAC>` → `connect <MAC>`

After pairing the device appears as a serial port:
- macOS: `/dev/cu.RobotESP32-SerialPort`
- Linux: `/dev/rfcomm0` (after `sudo rfcomm bind 0 <MAC>`)

Edit `PHASE_CONFIGS[2]` in [computer/main.py](computer/main.py) if your port differs.

### 3. Run the computer

```bash
python -m computer.main --phase 2
# or:
bash scripts/run.sh 2
```

---

## Phase 3 — Autonomous vision, physical robot + CAM

### 1. Flash both firmware boards

**Robot ESP32:**
```bash
cd robot
pio run --target upload
```

**ESP32-CAM:**
```bash
cd cam
pio run --target upload
```

> The ESP32-CAM uses the AI Thinker board. Hold the **GPIO0** button during
> power-on to enter flash mode, then release after upload starts.

### 2. Pair both Bluetooth devices

Repeat the pairing steps from Phase 2 for both `RobotESP32` and `RobotCAM`.

Update the port constants in `PHASE_CONFIGS[3]` inside [computer/main.py](computer/main.py):

```python
3: PhaseConfig(
    robot_port = "/dev/cu.RobotESP32-SerialPort",
    cam_port   = "/dev/cu.RobotCAM-SerialPort",
    ...
)
```

### 3. Run the computer

```bash
python -m computer.main --phase 3
# or:
bash scripts/run.sh 3
```

The vision pipeline is a stub until implemented — see [computer/vision/](computer/vision/) and [SPEC.md §7](SPEC.md).

---

## Component reference

| Component | Directory | Language | Entry point |
|-----------|-----------|----------|-------------|
| Computer  | `computer/` | Python ≥ 3.11 | `python -m computer.main --phase <1\|2\|3>` |
| Robot emulator | `emulator/` | Python ≥ 3.11 | `python emulator/src/main.py` |
| Robot firmware | `robot/` | C++ / PlatformIO | `cd robot && pio run --target upload` |
| CAM firmware | `cam/` | C++ / PlatformIO | `cd cam && pio run --target upload` |

---

## Troubleshooting

**Computer cannot connect to emulator (Phase 1)**
- Make sure the emulator is running before or shortly after the computer starts — it retries every 3 s.
- Check the port matches: emulator default is `5001`, computer default is `localhost:5001`.

**Bluetooth device not found (Phase 2/3)**
- Confirm the ESP32 is powered and the serial monitor shows `=== Ready ===`.
- On macOS, the `/dev/cu.*` entry only appears after the device is paired *and* the SPP profile is active (the ESP32 must be running).
- On Linux, run `sudo rfcomm bind 0 <MAC>` before launching the computer.

**ESP32-CAM upload fails**
- Hold GPIO0 to ground during power-on to force the board into bootloader mode.
- Use a lower upload speed: add `upload_speed = 115200` to `cam/platformio.ini`.

**Wheel motion is jerky or reversed**
- The rate limiter in `WheelController` ramps power at `MAX_DELTA_PER_TICK = 0.02` per tick at 50 Hz — full speed takes ~1 s from rest, which is by design.
- If left/right are swapped, swap the `LEFT_WHEEL` and `RIGHT_WHEEL` pin assignments in `robot/src/main.cpp`.
