# ESP32 Robot Emulator — Implementation Specification

This document is a **self-contained specification** for a standalone Python process that
emulates the ESP32-CAM robot.  It is intended to be implemented as a **separate project**
so that the computer-side application (`oop-communication-module/computer/`) can be
developed and tested end-to-end without physical hardware.

The emulator must be indistinguishable from the real robot from the computer app's point
of view: it speaks the same binary protocol over the same transport interface.

---

## 1. Testing roadmap context

The full project roadmap defines three test phases.  This emulator targets **Phase 1**
and is designed so that Phase 2 needs only the transport to be swapped (virtual serial
→ real Bluetooth).

| Phase | Input source | Robot | Goal |
|-------|-------------|-------|------|
| 1 — this spec | Keyboard arrow keys (emulator) | Emulated (this project) | Validate protocol and control logic with no hardware |
| 2 | Keyboard arrow keys | Physical ESP32 | Validate physical control over real Bluetooth |
| 3 | Computer vision (hand signs + subject tracking) | Physical ESP32 | Fully autonomous operation |

---

## 2. How the two processes talk

The real robot connects over **Bluetooth Classic SPP**, which the computer app sees as a
serial port.  The emulator replaces that physical link with a **virtual serial port pair**
created by `socat`.

### 2.1 Setting up the virtual link (run once, before either process)

```bash
socat -d -d \
  pty,raw,echo=0,link=/tmp/robot-emulator \
  pty,raw,echo=0,link=/tmp/robot-computer
```

| Symlink | Used by |
|---------|---------|
| `/tmp/robot-emulator` | the emulator process (this project) |
| `/tmp/robot-computer` | the computer app (`SerialTransport("/tmp/robot-computer")`) |

`socat` must stay running for the duration of the test.

### 2.2 Startup order

1. Start `socat`.
2. Start the **emulator** — it opens `/tmp/robot-emulator`.
3. Start the **computer app** — it opens `/tmp/robot-computer`.

Either process may start first; both should retry the port open in a loop until `socat`
is ready.

---

## 3. Binary protocol (complete, self-contained reference)

All multi-byte fields are **little-endian**.

### 3.1 Frame layout

```
Offset  Size  Field
──────  ────  ──────────────────────────────────────────────────────────
0       1     Start byte 1  — always 0xCA
1       1     Start byte 2  — always 0xFE
2       1     MSG_TYPE      — see §3.2
3       2     SEQ_NUM       — uint16-LE, per-sender counter, rolls over at 65535
5       4     PAYLOAD_LEN   — uint32-LE, number of payload bytes
9       N     PAYLOAD       — N = PAYLOAD_LEN bytes
9+N     2     CRC16         — uint16-LE (see §3.3)
11+N    1     End byte 1    — always 0xED
12+N    1     End byte 2    — always 0xED
```

Total frame size = 13 + N bytes.

### 3.2 Message types

| Value | Name | Direction | Description |
|-------|------|-----------|-------------|
| `0x01` | `IMAGE_CHUNK`   | Emulator → App | One 512-byte chunk of a JPEG frame |
| `0x02` | `DIRECTION_REF` | App → Emulator | Target angle + stop flag |
| `0x03` | `ACK`           | Both | Acknowledgement |
| `0x04` | `HEARTBEAT`     | Both | Keep-alive, empty payload |

### 3.3 CRC-16/CCITT (XModem)

- Polynomial: `0x1021`, initial value: `0x0000`, no reflection.
- Covers: `MSG_TYPE (1) + SEQ_NUM (2) + PAYLOAD_LEN (4) + PAYLOAD (N)`.

Reference Python implementation:

```python
def crc16(data: bytes) -> int:
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
        crc &= 0xFFFF
    return crc
```

### 3.4 Frame construction (Python pseudocode)

```python
import struct

def build_frame(msg_type: int, seq: int, payload: bytes) -> bytes:
    crc_input = struct.pack('<BHI', msg_type, seq, len(payload)) + payload
    crc = crc16(crc_input)
    return (
        b'\xCA\xFE'
        + struct.pack('<BHI', msg_type, seq, len(payload))
        + payload
        + struct.pack('<H', crc)
        + b'\xED\xED'
    )
```

### 3.5 Payload formats

#### IMAGE_CHUNK (`0x01`) — emulator sends

```
Offset  Size  Type     Field
──────  ────  ───────  ────────────────────────────────────────────────
0       2     uint16   frame_id      — monotonically increasing, per image
2       2     uint16   chunk_idx     — 0-based index of this chunk
4       2     uint16   total_chunks  — total chunks in this frame
6       4     uint32   total_size    — total JPEG byte count for this frame
10      M     bytes    jpeg_data     — raw JPEG bytes for this chunk (≤512 bytes)
```

Struct format string for the 10-byte header: `'<HHHI'`.

#### DIRECTION_REF (`0x02`) — emulator receives

```
Offset  Size  Type     Field
──────  ────  ───────  ────────────────────────────────────────────────
0       4     float32  angle_deg   — [-180.0, 180.0], clockwise from straight forward
4       1     uint8    stop        — 0 = move, 1 = stop
```

Struct format string: `'<fB'` (5 bytes total).

**Angle convention (matches arrow keys):**

| Key(s) pressed | angle_deg | stop |
|----------------|-----------|------|
| None | 0.0 | 1 |
| ↑ | 0.0 | 0 |
| ↓ | 180.0 | 0 |
| → | 90.0 | 0 |
| ← | −90.0 | 0 |
| ↑ + → | 45.0 | 0 |
| ↑ + ← | −45.0 | 0 |
| ↓ + → | 135.0 | 0 |
| ↓ + ← | −135.0 | 0 |

#### ACK (`0x03`)

```
Offset  Size  Type     Field
──────  ────  ───────  ────────────────────────────────────────────────
0       2     uint16   acked_seq   — SEQ_NUM being acknowledged
2       1     uint8    status      — 0=OK, 1=CRC_ERROR, 2=UNKNOWN_TYPE
```

Struct format string: `'<HB'` (3 bytes total).

#### HEARTBEAT (`0x04`)

Empty payload (`PAYLOAD_LEN = 0`).

---

## 4. Emulator behavioural specification

### 4.1 Overview

The emulator runs three concurrent **output** loops and one **input** loop.

| Loop | Interval | Action |
|------|----------|--------|
| Image loop | 150 ms (configurable) | Send `IMAGE_CHUNK` frames |
| Heartbeat loop | 1 000 ms | Send `HEARTBEAT` |
| Display loop | — | Show simulated robot state in the terminal |
| RX loop | continuous | Read `DIRECTION_REF`, `HEARTBEAT`, `ACK` |

All loops share a single serial port handle.  **TX must be protected by a mutex.**

### 4.2 Sequence number

One `uint16` TX counter, starting at 0, increments by 1 for every sent frame (any type),
rolls over at 65 535.  Incoming sequence numbers are not validated.

### 4.3 Image loop

#### 4.3.1 Image generation

Generate synthetic OpenCV images (BGR → JPEG-encoded).  Support a `--mode` CLI flag:

| Mode | Description | Use |
|------|-------------|-----|
| `static` | Solid grey frame with white crosshair | Minimal; verifies framing only |
| `blob` | Moving red circle on a dark background | Exercises the computer's CV pipeline |
| `files` | Cycle through JPEG files in a directory | Real-world images |

**`blob` mode — generation:**

```python
import cv2, math, time, numpy as np

t = time.monotonic()
cx = int(160 + 100 * math.cos(t * 0.5))
cy = int(120 +  60 * math.sin(t * 0.7))

frame = np.full((240, 320, 3), (30, 30, 30), dtype=np.uint8)
cv2.circle(frame, (cx, cy), 30, (0, 0, 200), -1)    # red blob (BGR)
# optionally overlay frame_id and timestamp as white text
_, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
jpeg_bytes = jpeg.tobytes()
```

#### 4.3.2 Chunking and transmission

```
total_chunks = ceil(len(jpeg_bytes) / 512)
for chunk_idx in range(total_chunks):
    offset     = chunk_idx * 512
    chunk_data = jpeg_bytes[offset : offset + 512]
    header     = struct.pack('<HHHI',
                     frame_id, chunk_idx, total_chunks, len(jpeg_bytes))
    payload    = header + chunk_data
    send IMAGE_CHUNK frame
    time.sleep(0)          # yield between chunks
frame_id = (frame_id + 1) & 0xFFFF
sleep until next image interval
```

### 4.4 Heartbeat loop

Send `HEARTBEAT` (empty payload) every 1 000 ms.

### 4.5 RX loop — DIRECTION_REF handling (Phase 1: arrow keys)

In Phase 1 the emulator generates `DIRECTION_REF` frames **itself** from keyboard
input, rather than receiving them from the computer app.  The computer app's
`CommunicationModule` will be sending them once the CV pipeline produces output, but
for Phase 1 the emulator IS the source of the direction signal.

**The emulator therefore acts as both sides of the DIRECTION_REF channel:**

```
Keyboard ──► KeyboardInput ──► DirectionRefPayload ──► (1) send to computer app
                                                   └──► (2) feed to SimulatedRobot
```

This lets you observe that:
- The computer app receives and decodes the frames correctly.
- `SimulatedRobot` shows the expected motion on screen.

#### 4.5.1 Keyboard capture (non-blocking, cross-platform)

Use `pynput` (recommended) or `curses` to read arrow key state without blocking.

```python
from pynput import keyboard

pressed = set()

def on_press(key):   pressed.add(key)
def on_release(key): pressed.discard(key)

listener = keyboard.Listener(on_press=on_press, on_release=on_release)
listener.start()
```

#### 4.5.2 Angle computation from key state

```python
from pynput.keyboard import Key

def keys_to_direction(pressed: set) -> tuple[float, bool]:
    """Returns (angle_deg, stop)."""
    up    = Key.up    in pressed
    down  = Key.down  in pressed
    right = Key.right in pressed
    left  = Key.left  in pressed

    if not any([up, down, right, left]):
        return 0.0, True        # no key → stop

    # Compute a unit vector from pressed keys, then convert to angle
    dy = (-1 if up   else 0) + (1 if down  else 0)   # forward = -y
    dx = ( 1 if right else 0) + (-1 if left else 0)

    import math
    angle_deg = math.degrees(math.atan2(dx, -dy))     # clockwise from forward
    return angle_deg, False
```

This naturally handles all diagonals without special-casing.

#### 4.5.3 Receiving DIRECTION_REF from the app (Phase 2 / 3 compatibility)

Even though Phase 1 uses keyboard input, the RX loop should still decode incoming
`DIRECTION_REF` frames so that the emulator works unchanged in Phase 2 (where the
computer app generates the signal from the same keyboard input):

| `msg_type` | Action |
|------------|--------|
| `0x02` DIRECTION_REF | Decode and forward to `SimulatedRobot`; log angle + stop |
| `0x03` ACK | Log `ACK seq={} status={}` |
| `0x04` HEARTBEAT | Log `HEARTBEAT received` |
| anything else | Log as unknown |

### 4.6 Simulated robot state

Maintain a `SimulatedRobot` that models the robot's response to the direction reference:

```python
BASE_SPEED         = 0.6    # power fraction at full forward
MAX_DELTA_PER_TICK = 0.02   # rate limiter, matches ESP32 WheelController
CONTROL_HZ         = 50
MAX_RPM            = 150.0
WHEEL_CIRCUMFERENCE = 0.20  # metres

@dataclasses.dataclass
class SimulatedRobot:
    current_left:  float = 0.0
    current_right: float = 0.0
    angle_deg:     float = 0.0
    stop:          bool  = True

    def set_ref(self, angle_deg: float, stop: bool) -> None:
        self.angle_deg = angle_deg
        self.stop      = stop

    def update(self) -> None:
        """Call at CONTROL_HZ. Applies same rate-limiter as the real WheelController."""
        if self.stop:
            target_l, target_r = 0.0, 0.0
        else:
            rad = math.radians(self.angle_deg)
            fwd  = BASE_SPEED * math.cos(rad)
            turn = BASE_SPEED * math.sin(rad)
            target_l = max(-1.0, min(1.0, fwd - turn))
            target_r = max(-1.0, min(1.0, fwd + turn))

        def slew(cur, tgt):
            d = tgt - cur
            d = max(-MAX_DELTA_PER_TICK, min(MAX_DELTA_PER_TICK, d))
            return cur + d

        self.current_left  = slew(self.current_left,  target_l)
        self.current_right = slew(self.current_right, target_r)

    @property
    def speed_mps(self) -> float:
        avg_rpm = (self.current_left + self.current_right) / 2.0 * MAX_RPM
        return avg_rpm * WHEEL_CIRCUMFERENCE / 60.0
```

---

## 5. Emulator internal architecture

```
EmulatorApp
├── SerialLink          — opens /tmp/robot-emulator, read/write with TX mutex
├── FrameEncoder        — builds binary frames (implement from spec §3)
├── FrameDecoder        — streaming decoder  (implement from spec §3)
├── KeyboardInput       — non-blocking arrow key state (pynput)
├── ImageGenerator      — produces JPEG bytes (static / blob / files mode)
├── SimulatedRobot      — rate-limited wheel model
└── threads
    ├── rx_thread       — reads serial, decodes frames, updates SimulatedRobot
    ├── image_thread    — generates frame, chunks, sends IMAGE_CHUNK
    ├── heartbeat_thread— sends HEARTBEAT every 1 000 ms
    ├── control_thread  — calls SimulatedRobot.update() at CONTROL_HZ (50 Hz)
    └── keyboard_thread — reads KeyboardInput, sends DIRECTION_REF at ~20 Hz
```

All threads share `SerialLink` (TX mutex) and `SimulatedRobot` (state mutex).

---

## 6. Suggested project layout

```
robot-emulator/               ← new, separate project directory
├── README.md
├── requirements.txt          numpy, opencv-python, pyserial, pynput
└── src/
    ├── main.py               — CLI entry point
    ├── protocol.py           — FrameEncoder + FrameDecoder (implement from §3)
    ├── serial_link.py        — serial port wrapper with TX mutex
    ├── simulated_robot.py    — SimulatedRobot (rate-limited wheel model)
    ├── image_generator.py    — static / blob / files image generation
    ├── keyboard_input.py     — non-blocking arrow key reading (pynput)
    └── emulator.py           — spawns all threads, wires components together
```

`protocol.py` must be a **fresh re-implementation from this spec** — do not import
or reference anything from `oop-communication-module`.

---

## 7. CLI interface

```
python src/main.py [OPTIONS]

Options:
  --port PATH        Virtual serial port  [default: /tmp/robot-emulator]
  --mode MODE        Image mode: static | blob | files  [default: blob]
  --image-dir PATH   Directory of JPEG files (required when --mode=files)
  --fps FLOAT        Target image frame rate  [default: 6.0]
  --verbose          Print every sent/received frame to stdout
```

Startup banner:
```
[EMU] Opening /tmp/robot-emulator …
[EMU] Serial port open. Starting loops.
[EMU] Mode: blob  FPS: 6.0
[EMU] Arrow keys: ↑ forward | ↓ backward | ← left | → right | combinations ok
[EMU] No key pressed = STOP
```

Status line (refresh every 0.5 s, in-place terminal update):
```
[EMU] angle=  45.0°  stop=0  L=+0.38  R=+0.77  speed=+0.43 m/s  tx=142  rx=18
```

---

## 8. Integration test procedure

### Prerequisites

```bash
pip install numpy opencv-python pyserial pynput
```

### Step 1 — virtual link

```bash
socat -d -d \
  pty,raw,echo=0,link=/tmp/robot-emulator \
  pty,raw,echo=0,link=/tmp/robot-computer
```

### Step 2 — start the emulator

```bash
cd robot-emulator
python src/main.py --mode blob --fps 6
```

### Step 3 — start the computer app

In `oop-communication-module/computer/src/main.py` set:

```python
TRANSPORT   = "serial"
SERIAL_PORT = "/tmp/robot-computer"
SHOW_PREVIEW = True
```

Then:
```bash
python src/main.py
```

### Step 4 — verify

| Observation | Location |
|-------------|----------|
| Live window opens showing the moving red blob | computer app (OpenCV) |
| Green bounding box appears around the blob | computer app (OpenCV) |
| Pressing ↑ → emulator logs `angle=0.0 stop=0` | emulator terminal |
| Pressing → → emulator logs `angle=90.0 stop=0` | emulator terminal |
| Pressing ↑+→ → emulator logs `angle=45.0 stop=0` | emulator terminal |
| No key pressed → emulator logs `stop=1`, `L=0.00 R=0.00` (after slew) | emulator terminal |
| Heartbeat received every ~1 s | emulator terminal |

### Step 5 — fault injection tests

| Test | How | Expected |
|------|-----|----------|
| Link loss | Kill `socat` | Computer app reconnects; emulator logs port error |
| Chunk drop | Skip sending chunk N in code | Assembler evicts incomplete frame after 2 s |
| CRC error | Flip a byte in a sent frame | Receiver silently drops the frame |
| Rapid direction change | Mash multiple arrow keys | `SimulatedRobot` shows smooth slew (not instant jump) |

---

## 9. What this emulator does NOT need to implement

- Any Bluetooth stack.
- Real encoder simulation (wheel pulses are not observable from the computer side).
- Camera hardware.
- ACK sending (the computer app does not require ACKs to function).
- OTA or configuration commands.
