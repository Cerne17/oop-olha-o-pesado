# Robot Emulator — Implementation Specification (v2)

> **Supersedes:** `EMULATOR_SPEC.md` (old spec used socat, `DIRECTION_REF` with a
> `stop` bool, and had the keyboard living inside the emulator process). All of
> that is replaced by this document.
>
> **Scope:** Phase 1 robot emulator only. CAM emulator is out of scope and will
> be specified separately when Phase 3 testing begins.

---

## 1. Overview

Phase 1 replaces physical hardware with two Python processes that communicate
over a **TCP loopback socket**:

```
┌────────────────────────────────────────┐     TCP localhost:5001
│  computer process                      │ ─────────────────────►  ┌─────────────────────────┐
│  (python -m computer.main --phase 1)   │                          │  robot emulator process  │
│                                        │ ◄─────────────────────── │  (python -m emulator.robot) │
│  KeyboardController                    │     ACK + HEARTBEAT      └─────────────────────────┘
│       │ ControlSignal                  │
│       ▼                                │
│  RobotSender (TCPTransport)            │
└────────────────────────────────────────┘
```

The emulator is **indistinguishable from the real robot** from the computer's
point of view: it speaks the same binary protocol (`CONTROL_REF / ACK / HEARTBEAT`)
and lives at a TCP address instead of a Bluetooth serial port. No code change is
needed in the computer package other than selecting `transport = "tcp"` in the
Phase 1 config.

---

## 2. Required change in the computer/ package

Before the emulator can be used, a `TCPTransport` must be added to
`computer/communication/transport.py`. This is the only computer-side change
required.

### 2.1 TCPTransport specification

`TCPTransport` is a **TCP client**. The emulator is the server. This mirrors the
real-world model: the ESP32 is always-on and the computer connects to it.

```
computer/communication/transport.py
------------------------------------
class TCPTransport(Transport):
    def __init__(self, host: str, port: int) -> None: ...
    def connect(self) -> None:
        # create AF_INET SOCK_STREAM socket
        # connect to (host, port), raise ConnectionError on failure
        # set socket to non-blocking after connect
    def disconnect(self) -> None: ...
    def send(self, data: bytes) -> None:
        # sendall(); raise ConnectionError on OSError
    def receive_available(self, max_bytes: int = 4096) -> bytes:
        # non-blocking recv(); return b'' on BlockingIOError
    def is_connected(self) -> bool: ...
```

### 2.2 Changes to computer/main.py

Update `_make_transport()` to handle `"tcp"`:

```python
if kind == "tcp":
    host, port = address.rsplit(":", 1)
    return TCPTransport(host, int(port))
```

Update `PHASE_CONFIGS[1]`:

```python
1: PhaseConfig(
    robot_port      = "localhost:5001",
    robot_transport = "tcp",
    cam_port        = None,
),
```

---

## 3. Binary protocol (Link B — Computer <-> Robot)

Identical wire framing to the computer's `computer/communication/protocol.py`.
The emulator carries its own self-contained copy of encoder/decoder so it can
run without installing the computer package.

### 3.1 Frame layout

```
Offset  Size  Field
------  ----  ---------------------------------------------------
0       1     Start byte 1  -- always 0xCA
1       1     Start byte 2  -- always 0xFE
2       1     MSG_TYPE      -- see §3.2
3       2     SEQ_NUM       -- uint16-LE, per-sender, rolls over at 65535
5       4     PAYLOAD_LEN   -- uint32-LE, byte count of PAYLOAD
9       N     PAYLOAD       -- N = PAYLOAD_LEN bytes
9+N     2     CRC16         -- uint16-LE (see §3.3), covers bytes 2..9+N-1
11+N    1     End byte 1    -- always 0xED
12+N    1     End byte 2    -- always 0xED
```

Total frame size = 13 + N bytes.

### 3.2 Message types (Link B)

| Value  | Name          | Direction          | Description                        |
|--------|---------------|--------------------|------------------------------------|
| `0x01` | `CONTROL_REF` | Computer -> Robot  | Target angle + speed reference     |
| `0x02` | `ACK`         | Robot -> Computer  | Acknowledgement                    |
| `0x03` | `HEARTBEAT`   | Both               | Keep-alive, empty payload          |

### 3.3 CRC-16/CCITT (XModem)

Polynomial: `0x1021`, initial value: `0x0000`, no reflection.
Covers: `MSG_TYPE (1) + SEQ_NUM (2) + PAYLOAD_LEN (4) + PAYLOAD (N)`.

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

### 3.4 Payload formats

#### CONTROL_REF (`0x01`) -- emulator receives

```
Offset  Size  Type     Field
------  ----  -------  ------------------------------------------------
0       4     float32  angle_deg   -- [-180.0, 180.0], clockwise from forward
4       4     float32  speed_ref   -- [-1.0, 1.0], negative = reverse
```

Struct format: `'<ff'` (8 bytes total).

#### ACK (`0x02`) -- emulator sends

```
Offset  Size  Type     Field
------  ----  -------  ------------------------------------------------
0       2     uint16   acked_seq  -- SEQ_NUM of the frame being acknowledged
2       1     uint8    status     -- 0=OK  1=CRC_ERROR  2=UNKNOWN_TYPE
```

Struct format: `'<HB'` (3 bytes total).

#### HEARTBEAT (`0x03`) -- both directions

Empty payload (`PAYLOAD_LEN = 0`).

---

## 4. Emulator behavioural specification

### 4.1 Startup and connection

The emulator opens a **TCP server socket** on `0.0.0.0:PORT` (default 5001) and
waits for exactly one client connection. Once the computer process connects, it
starts all worker threads. If the connection is lost it closes the accepted
socket and loops back to `accept()`, waiting for a reconnect.

### 4.2 RX loop

Reads from the TCP socket in a tight loop (non-blocking, 5 ms sleep when no
data). Feeds bytes into a `FrameDecoder` state machine. On each complete frame:

| `MSG_TYPE`    | Action                                                                    |
|---------------|---------------------------------------------------------------------------|
| `CONTROL_REF` | Decode `(angle_deg, speed_ref)`; call `SimulatedRobot.set_ref()`; send ACK |
| `HEARTBEAT`   | Record receive time; reply with HEARTBEAT if none sent in the last 1 s     |
| `ACK`         | Log `[RX] ACK acked_seq=N status=S`                                        |
| Bad CRC       | Send ACK with `status=1`; discard                                          |
| Unknown type  | Send ACK with `status=2`; discard                                          |

### 4.3 Heartbeat loop

Sends a `HEARTBEAT` frame every 1 000 ms, regardless of received traffic.
This keeps the computer's heartbeat watchdog (`HEARTBEAT_TIMEOUT_MS = 5 s`)
satisfied even when no `CONTROL_REF` frames arrive.

### 4.4 Control loop

Calls `SimulatedRobot.update()` at `CONTROL_HZ = 50` Hz (20 ms tick). This
rate-limits the wheel powers to match the ESP32 `WheelController`.

### 4.5 Display loop

Refreshes a one-line status to stdout every 500 ms (overwrite the same line):

```
[EMU] angle=  45.0 deg  speed=+0.50  L=+0.38  R=+0.77  speed_mps=+0.43  tx=142  rx=18
```

All TX must be guarded by a single `threading.Lock` shared between the RX
loop, heartbeat loop, and any future TX path.

---

## 5. SimulatedRobot — wheel model

The Python implementation mirrors `robot/src/control/WheelController.cpp`
exactly. Constants must stay in sync with the C++ header.

```python
MAX_DELTA_PER_TICK  = 0.02   # matches WheelController.h
CONTROL_HZ          = 50
MAX_RPM             = 150.0
WHEEL_CIRCUMFERENCE = 0.20   # metres
```

### 5.1 Target computation (per tick)

```python
def _compute_targets(self, angle_deg: float, speed_ref: float) -> tuple[float, float]:
    if speed_ref == 0.0:
        return 0.0, 0.0
    rad    = math.radians(angle_deg)
    fwd    = speed_ref * math.cos(rad)
    turn   = speed_ref * math.sin(rad)
    left   = max(-1.0, min(1.0, fwd - turn))
    right  = max(-1.0, min(1.0, fwd + turn))
    return left, right
```

### 5.2 Rate limiter (slew)

```python
def _slew(self, current: float, target: float) -> float:
    delta = target - current
    delta = max(-MAX_DELTA_PER_TICK, min(MAX_DELTA_PER_TICK, delta))
    return current + delta
```

### 5.3 Emergency stop

`set_ref(angle_deg=0.0, speed_ref=0.0)` drives both targets to `0.0`. The slew
ramps the actual powers down over ~50 ticks (1 s), identical to the real
`emergencyStop()` call on the ESP32.

### 5.4 Derived output

```python
@property
def speed_mps(self) -> float:
    avg_power = (self._current_left + self._current_right) / 2.0
    avg_rpm   = avg_power * MAX_RPM
    return avg_rpm * WHEEL_CIRCUMFERENCE / 60.0
```

---

## 6. Threading model

```
Main thread
  |-- accept loop: wait for one TCP client; restart on disconnect
  |
  +-- rx-loop         reads TCP socket, decodes frames, sends ACK/HB replies
  +-- hb-loop         sends HEARTBEAT every 1 000 ms
  +-- control-loop    calls SimulatedRobot.update() at 50 Hz
  +-- display-loop    prints status line every 500 ms
```

All threads are daemon threads. A single `threading.Lock` (`_tx_lock`) guards
all writes to the TCP socket.

---

## 7. Project layout

```
emulator/
├── SPEC.md                   -- this document (new)
├── EMULATOR_SPEC.md          -- old spec (superseded, kept for reference)
├── requirements.txt          -- pyserial removed; only: pynput (optional), none else
└── src/
    ├── main.py               -- entry point: python src/main.py [--port 5001]
    ├── protocol.py           -- FrameEncoder + FrameDecoder (self-contained copy)
    ├── tcp_link.py           -- TCP server socket wrapper with TX lock
    ├── simulated_robot.py    -- SimulatedRobot (updated: speed_ref formula)
    └── robot_emulator.py     -- spawns all threads, wires components together
```

`protocol.py` must remain a **self-contained copy** of the wire format — do not
import from `computer/`. The emulator must be runnable without installing the
computer package.

---

## 8. CLI

```
python src/main.py [OPTIONS]

Options:
  --port INT    TCP port to listen on  [default: 5001]
  --verbose     Log every sent/received frame
```

Startup banner:

```
[EMU] Robot emulator starting — listening on 0.0.0.0:5001
[EMU] Waiting for computer to connect...
[EMU] Computer connected from 127.0.0.1
[EMU] All loops running. Ctrl+C to stop.
```

Status line (in-place, every 500 ms):

```
[EMU] angle=  45.0 deg  speed=+0.50  L=+0.38  R=+0.77  speed_mps=+0.43 m/s  tx=142  rx=18
```

---

## 9. How to run Phase 1

**Terminal 1 — robot emulator:**
```bash
cd emulator
python src/main.py --port 5001
```

**Terminal 2 — computer (manual keyboard):**
```bash
python -m computer.main --phase 1
```

Startup order does not matter: the computer's `TCPTransport` retries the
connection every 3 s until the emulator is ready.

---

## 10. Expected observations during a Phase 1 test

| Action                       | Expected observation                                      |
|------------------------------|-----------------------------------------------------------|
| Start both processes         | Emulator prints "Computer connected"; computer prints "[PHASE 1] Running" |
| Press arrow up               | Emulator: `angle=0.0 speed=+1.00 L=...` ramping up       |
| Press arrow right            | Emulator: `angle=90.0` right motor higher than left       |
| Release all keys             | Emulator: `speed=+0.00`, L and R ramp to 0 over ~1 s     |
| Press diagonal (up + right)  | Emulator: `angle=45.0`                                    |
| Kill emulator (Ctrl+C)       | Computer: reconnect retries every 3 s                     |
| Kill computer (Ctrl+C)       | Emulator: loops back to `accept()` waiting for reconnect  |

---

## 11. What is NOT in scope for Phase 1

- CAM emulator (deferred to Phase 3 prep)
- Image generation or streaming
- Vision pipeline
- ACK retransmission or reliability guarantees
- Bluetooth stack
- Real encoder feedback
