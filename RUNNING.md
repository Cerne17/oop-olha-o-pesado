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

For full wiring diagrams, driver installation, bootloader mode instructions,
and configuration reference see **[FIRMWARE.md](FIRMWARE.md)**.

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

> Full wiring and driver setup: [FIRMWARE.md §2–4](FIRMWARE.md).

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

> The ESP32-CAM uses the AI Thinker board and requires a separate FTDI adapter
> and a GPIO0–GND jumper to enter flash mode. See [FIRMWARE.md §3–5](FIRMWARE.md)
> for the full wiring diagram and step-by-step procedure.

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

## run.sh — helper script

`scripts/run.sh` is the recommended way to launch the computer module.
It activates the virtual environment automatically and prints phase-specific
reminders before starting.

```
bash scripts/run.sh <phase>

Arguments:
  phase   1 | 2 | 3

Phase descriptions:
  1   Manual control / TCP loopback to robot emulator
  2   Manual control / physical robot over Bluetooth
  3   Autonomous vision / physical robot + CAM over Bluetooth
```

What the script does:
1. Resolves the repo root from its own path — safe to call from any directory.
2. Sources `.venv/bin/activate` if a `.venv` directory exists; warns if not.
3. Prints a phase-specific pre-flight reminder (e.g. "start the emulator first").
4. Calls `exec python -m computer.main --phase N` — the script process is
   replaced by Python, so Ctrl+C reaches the Python process directly.

If you prefer to run without the script:
```bash
source .venv/bin/activate
python -m computer.main --phase 1
```

---

## Component reference

| Component | Directory | Language | Entry point |
|-----------|-----------|----------|-------------|
| Computer  | `computer/` | Python ≥ 3.11 | `python -m computer.main --phase <1\|2\|3>` |
| Robot emulator | `emulator/` | Python ≥ 3.11 | `python emulator/src/main.py` |
| Robot firmware | `robot/` | C++ / PlatformIO | `cd robot && pio run --target upload` |
| CAM firmware | `cam/` | C++ / PlatformIO | `cd cam && pio run --target upload` |

---

## Developer skills

Project skills live in `.claude/skills/` and are auto-discovered by Claude Code.
Invoke any skill with `/skill-name` in the Claude Code REPL, or run `/skills` to see the full index.

| Task | Skill |
|------|-------|
| Something broke in the computer communication layer | `/debug-computer-comm` |
| Add a new transport (WebSocket, UDP, …) | `/implement-transport` |
| Add a new wire message type (one link) | `/add-message-type` |
| Add a new wire message type (Python + C++ + emulator) | `/sync-message-type` |
| Implement a vision detector | `/implement-detector` |
| Implement a control strategy | `/implement-strategy` |
| Debug robot firmware | `/debug-robot-comm` |
| Add a new drive mode to the robot | `/add-motion-mode` |
| Debug the ESP32-CAM firmware | `/debug-cam-comm` |
| Debug the Phase 1 emulator | `/debug-emulator` |
| Add mock behaviour to the emulator | `/extend-emulator` |
| Firmware upload fails (`Failed to connect`) | `/debug-upload` |
| Serial monitor shows garbage or permission denied | `/debug-serial` |
| ESP32-CAM: `camera init failed` or no frames | `/debug-cam-init` |
| Bluetooth device not found or port missing | `/debug-bluetooth` |
| Change motor pins, BT name, FPS, or image quality | `/configure-firmware` |

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
