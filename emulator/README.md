# ESP32 Robot Emulator

A Python process that emulates an ESP32-CAM robot over a virtual serial port.
It speaks the same binary protocol as the real hardware, so the computer-side
application (`oop-communication-module/computer/`) can be developed and tested
end-to-end without any physical device.

---

## Requirements

| Dependency | Purpose |
|---|---|
| `numpy` | Image array manipulation |
| `opencv-python` | JPEG encoding and synthetic frame generation |
| `pyserial` | Virtual serial port I/O |
| `pynput` | Non-blocking keyboard input |

Install everything at once:

```bash
pip install -r requirements.txt
```

> **macOS note:** `pynput` requires accessibility permissions.
> Go to **System Settings → Privacy & Security → Accessibility** and allow your
> terminal application.

---

## Quick start

### Step 1 — Create the virtual serial link

The emulator and the computer app communicate through a virtual serial port pair
created by `socat`. Run this once and leave it running in its own terminal:

```bash
socat -d -d \
  pty,raw,echo=0,link=/tmp/robot-emulator \
  pty,raw,echo=0,link=/tmp/robot-computer
```

| Symlink | Used by |
|---|---|
| `/tmp/robot-emulator` | this emulator |
| `/tmp/robot-computer` | the computer app |

### Step 2 — Start the emulator

```bash
cd oop-emulator
python src/main.py --mode blob --fps 6
```

You should see:

```
[EMU] Opening /tmp/robot-emulator …
[EMU] Serial port open. Starting loops.
[EMU] Mode: blob  FPS: 6.0
[EMU] Arrow keys: ↑ forward | ↓ backward | ← left | → right | combinations ok
[EMU] No key pressed = STOP
```

And a live status line that refreshes every 0.5 s:

```
[EMU] angle=  +0.0°  stop=1  L=+0.00  R=+0.00  speed=+0.00 m/s  tx=12  rx=3
```

### Step 3 — Start the computer app

In `oop-communication-module/computer/src/main.py` configure:

```python
TRANSPORT    = "serial"
SERIAL_PORT  = "/tmp/robot-computer"
SHOW_PREVIEW = True
```

Then:

```bash
python src/main.py
```

### Step 4 — Drive the robot

With the emulator terminal focused, use the arrow keys:

| Key(s) | Behaviour | angle |
|---|---|---|
| No key | Stop | — |
| ↑ | Forward | 0° |
| ↓ | Backward | 180° |
| → | Turn right | 90° |
| ← | Turn left | −90° |
| ↑ + → | Forward-right diagonal | 45° |
| ↑ + ← | Forward-left diagonal | −45° |
| ↓ + → | Backward-right diagonal | 135° |
| ↓ + ← | Backward-left diagonal | −135° |

Press **ESC** (or Ctrl-C) to quit.

---

## CLI reference

```
python src/main.py [OPTIONS]

Options:
  --port PATH        Virtual serial port          [default: /tmp/robot-emulator]
  --mode MODE        Image mode: static|blob|files [default: blob]
  --image-dir PATH   JPEG directory (required for --mode=files)
  --fps FLOAT        Target frame rate             [default: 6.0]
  --verbose          Print every sent/received frame
```

### Image modes

| Mode | What it generates | Good for |
|---|---|---|
| `blob` | Moving red circle on a dark background | Testing the CV pipeline |
| `static` | Grey frame with white crosshair | Minimal protocol smoke test |
| `files` | Cycles through JPEG files in a directory | Real-world images |

**Example — files mode:**

```bash
python src/main.py --mode files --image-dir ~/my-images --fps 4
```

---

## Project layout

```
oop-emulator/
├── README.md
├── requirements.txt
└── src/
    ├── main.py             CLI entry point (argparse)
    ├── emulator.py         Spawns all threads, wires components together
    ├── protocol.py         FrameEncoder + FrameDecoder (binary protocol)
    ├── serial_link.py      Serial port wrapper with TX mutex
    ├── simulated_robot.py  Rate-limited wheel model (matches ESP32 WheelController)
    ├── image_generator.py  Synthetic JPEG generation (static / blob / files)
    └── keyboard_input.py   Non-blocking arrow key reading (pynput)
```

### Internal threads

| Thread | Rate | Role |
|---|---|---|
| `rx_thread` | continuous | Reads serial, decodes frames, updates `SimulatedRobot` |
| `image_thread` | `--fps` (default 6 Hz) | Generates JPEG, chunks it, sends `IMAGE_CHUNK` frames |
| `heartbeat_thread` | 1 Hz | Sends `HEARTBEAT` |
| `control_thread` | 50 Hz | Calls `SimulatedRobot.update()` (slew rate limiter) |
| `keyboard_thread` | 20 Hz | Reads keys, sends `DIRECTION_REF`, feeds `SimulatedRobot` |
| `display_thread` | 2 Hz | Refreshes the status line in-place |

---

## Binary protocol overview

All frames share the same structure:

```
0xCA 0xFE | MSG_TYPE | SEQ_NUM (u16-LE) | PAYLOAD_LEN (u32-LE) | PAYLOAD | CRC16 (u16-LE) | 0xED 0xED
```

| MSG_TYPE | Value | Direction | Description |
|---|---|---|---|
| `IMAGE_CHUNK` | `0x01` | Emulator → App | One 512-byte chunk of a JPEG frame |
| `DIRECTION_REF` | `0x02` | App → Emulator | Target angle + stop flag |
| `ACK` | `0x03` | Both | Acknowledgement |
| `HEARTBEAT` | `0x04` | Both | Keep-alive, empty payload |

CRC is **CRC-16/CCITT XModem** (poly `0x1021`, init `0x0000`) covering
`MSG_TYPE + SEQ_NUM + PAYLOAD_LEN + PAYLOAD`.

See [src/protocol.py](src/protocol.py) for the complete implementation.

---

## Testing phases

| Phase | Input | Robot | Goal |
|---|---|---|---|
| **1 (this project)** | Arrow keys (emulator generates the signal) | This emulator | Validate protocol and control logic — no hardware needed |
| 2 | Arrow keys | Physical ESP32 | Validate physical control over real Bluetooth |
| 3 | Computer vision (hand signs + tracking) | Physical ESP32 | Fully autonomous |

The emulator is designed so that Phase 2 only requires swapping the transport
(virtual serial → real Bluetooth serial port). No other changes are needed.

---

## Fault injection

| Scenario | How to reproduce | Expected outcome |
|---|---|---|
| Link loss | Kill the `socat` process | Computer app reconnects; emulator logs port error |
| Chunk drop | Comment out one `send()` call in `image_thread` | Assembler evicts the incomplete frame after 2 s |
| CRC error | Flip a byte in a built frame before sending | Receiver silently drops the frame |
| Rapid direction change | Mash multiple arrow keys quickly | Status line shows smooth slew, no instant jumps |

---

## Troubleshooting

**`Cannot open /tmp/robot-emulator`**
`socat` is not running or has not yet created the symlinks. Start `socat` first and wait for the `PTY is /dev/ttys…` lines before launching the emulator.

**`pynput` does not detect key presses**
Grant accessibility permissions to your terminal (macOS: System Settings → Privacy & Security → Accessibility).

**High CPU usage**
Lower `--fps` or reduce `CONTROL_HZ` in `simulated_robot.py`. The default 6 FPS / 50 Hz control loop is intentionally lightweight.
