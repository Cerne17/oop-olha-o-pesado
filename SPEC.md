# Robot Vision System — Implementation Specification

> **Purpose:** Authoritative design document for agent-driven implementation.
> Each module section is self-contained: an agent given only that section plus
> the Shared Protocol and Types sections can implement the module in full.

---

## 1. System Overview

### 1.1 Hardware Units

| Unit | Hardware | Language | Responsibility |
|------|----------|----------|----------------|
| Computer | PC (macOS / Linux) | Python ≥ 3.11 | Vision pipeline · Control logic · Transport orchestration |
| Camera | ESP32-CAM | C++ / PlatformIO | JPEG capture · Frame chunking · ACK-based streaming |
| Robot | ESP32 | C++ / PlatformIO | Motor control · Wheel power smoothing |

The Camera and Robot are **two separate physical boards** connected to the Computer over independent serial/Bluetooth links.

### 1.2 Physical Topology

```
┌──────────────────────────────────────────────────────────────────┐
│  ESP32-CAM  (cam/)                                               │
│  cam/communication/ ──► IMAGE_CHUNK ──────────────────────────   │
│                    ◄─── ACK + HEARTBEAT ──────────────────────   │
└──────────────────────────────────────────────────────────────────┘
                           Link A (BT SPP / Serial)
┌──────────────────────────────────────────────────────────────────┐
│  Computer  (computer/)                                           │
│                                                                  │
│  communication/cam_receiver  ──[Frame]──► vision/processor       │
│                                                 │                │
│                                        [FrameResult]             │
│                                                 ▼                │
│  communication/robot_sender ◄─[ControlSignal]── vision/strategy  │
│                                                                  │
│  manual/keyboard ───────────[ControlSignal]──► robot_sender      │
└──────────────────────────────────────────────────────────────────┘
                           Link B (BT SPP / Serial)
┌──────────────────────────────────────────────────────────────────┐
│  ESP32 Robot  (robot/)                                           │
│  robot/communication/ ──► robot/control/                         │
└──────────────────────────────────────────────────────────────────┘
```

### 1.3 Data Flow Summary

| Direction | Message | Payload | Rate |
|-----------|---------|---------|------|
| CAM → Computer | `IMAGE_CHUNK` | 512-byte JPEG slice | 6–10 FPS |
| Computer → CAM | `ACK` | frame_id + status | once per assembled frame |
| Both (Link A) | `HEARTBEAT` | empty | 1 Hz |
| Computer → Robot | `CONTROL_REF` | angle_deg + speed_ref | up to 20 Hz |
| Both (Link B) | `HEARTBEAT` | empty | 1 Hz |

### 1.4 Modes of Operation

| Mode | ControlSignal source | Activated by |
|------|----------------------|--------------|
| **Manual** | `manual/keyboard.py` | `python -m computer.manual.main` |
| **Autonomous** | `vision/strategy.py` | `python -m computer.main` |

In both modes `RobotSender` is the single point that writes to the robot link.

---

## 2. Repository Structure

```
.
├── computer/                     Python package — all host-side logic
│   ├── __init__.py
│   ├── types/                    Shared interfaces and data types (NO business logic)
│   │   ├── __init__.py
│   │   ├── signals.py            Frame, ControlSignal dataclasses
│   │   ├── detections.py         Detection, FrameResult dataclasses
│   │   ├── observers.py          Observer ABCs + Observable mixins
│   │   └── transport.py          Transport ABC
│   ├── communication/            Network layer — protocol, assembly, link management
│   │   ├── __init__.py
│   │   ├── protocol.py           Binary frame encoder + decoder (no I/O)
│   │   ├── assembler.py          ImageAssembler — chunks → complete JPEG
│   │   ├── cam_receiver.py       CamReceiver — manages Link A
│   │   └── robot_sender.py       RobotSender  — manages Link B
│   ├── vision/                   Vision pipeline
│   │   ├── __init__.py
│   │   ├── processor.py          VisionProcessor — frame queue + worker thread
│   │   ├── strategy.py           ControlStrategy — FrameResult → ControlSignal
│   │   └── detectors/
│   │       ├── __init__.py
│   │       ├── base.py           Detector ABC
│   │       └── colour_blob.py    ColourBlobDetector
│   ├── manual/                   Manual control — arrow-key controller
│   │   ├── __init__.py
│   │   ├── keyboard.py           KeyboardController
│   │   └── main.py               Entry point (manual mode)
│   └── main.py                   Entry point (autonomous vision mode)
│
├── robot/                        ESP32 firmware — motor control
│   ├── platformio.ini
│   └── src/
│       ├── main.cpp
│       ├── types/
│       │   ├── Protocol.h        Wire constants, ControlRefPayload, AckPayload, crc16
│       │   └── MotorTypes.h      WheelPins, WheelSpeeds structs
│       ├── communication/
│       │   ├── RobotComm.h
│       │   └── RobotComm.cpp     FreeRTOS BT receive task → WheelController
│       └── control/
│           ├── WheelController.h
│           └── WheelController.cpp  Rate-limited differential drive
│
├── cam/                          ESP32-CAM firmware — image streaming
│   ├── platformio.ini
│   └── src/
│       ├── main.cpp
│       ├── types/
│       │   └── Protocol.h        Same wire constants (copied — no cross-build)
│       └── communication/
│           ├── CamComm.h
│           └── CamComm.cpp       FreeRTOS capture + chunk + ACK-receive tasks
│
├── pyproject.toml
└── requirements.txt
```

---

## 3. Shared Binary Protocol

Both Link A (Computer ↔ CAM) and Link B (Computer ↔ Robot) use **identical wire framing**. Only the message type values differ per link; see §3.3 and §3.4.

### 3.1 Frame Format

All multi-byte integers are **little-endian**.

```
Offset   Size   Field
──────   ────   ────────────────────────────────────────────────────────
0        1      START_1  = 0xCA
1        1      START_2  = 0xFE
2        1      MSG_TYPE (uint8)
3        2      SEQ_NUM  (uint16, rolls over at 65535)
5        4      PAYLOAD_LEN (uint32)
9        N      PAYLOAD (variable)
9+N      2      CRC16 (uint16, LE) — see §3.2
9+N+2    1      END_1 = 0xED
9+N+3    1      END_2 = 0xED
```

Minimum frame size (empty payload): **13 bytes**.

### 3.2 CRC-16/CCITT (XModem)

- Polynomial: `0x1021`  |  Initial value: `0x0000`  |  No input/output reflection
- **Covers:** `MSG_TYPE(1) + SEQ_NUM(2) + PAYLOAD_LEN(4) + PAYLOAD(N)`

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

### 3.3 Message Types — Link A (CAM ↔ Computer)

| Name | Value | Direction | Payload struct |
|------|-------|-----------|----------------|
| `IMAGE_CHUNK` | `0x01` | CAM → Computer | `ImageChunkHeader` (10 B) + raw JPEG bytes |
| `ACK` | `0x02` | Computer → CAM | `AckPayload` (3 B) |
| `HEARTBEAT` | `0x03` | Both | empty |

### 3.4 Message Types — Link B (Computer ↔ Robot)

| Name | Value | Direction | Payload struct |
|------|-------|-----------|----------------|
| `CONTROL_REF` | `0x01` | Computer → Robot | `ControlRefPayload` (8 B) |
| `ACK` | `0x02` | Both | `AckPayload` (3 B) |
| `HEARTBEAT` | `0x03` | Both | empty |

### 3.5 Payload Layouts (packed — no padding)

**`ImageChunkHeader`** — 10 bytes

```
uint16_t  frame_id       monotonically increasing frame identifier (wraps at 65535)
uint16_t  chunk_idx      0-based chunk index within this frame
uint16_t  total_chunks   total chunks that make up this frame
uint32_t  total_size     total JPEG byte count for the full frame
```
Followed immediately by raw JPEG bytes (up to 512 bytes per chunk).

**`ControlRefPayload`** — 8 bytes

```
float32   angle_deg   movement direction, clockwise from straight forward
                      range: [-180.0, 180.0]
                        0° = straight forward
                       90° = pivot right
                      -90° = pivot left
                      ±180° = straight backward
float32   speed_ref   speed magnitude
                      range: [-1.0, 1.0]
                       +1.0 = maximum forward speed
                        0.0 = stopped
                       -1.0 = maximum reverse speed
```

**`AckPayload`** — 3 bytes

```
uint16_t  acked_seq   SEQ_NUM of the frame being acknowledged
uint8_t   status      0 = OK
                      1 = CRC_ERROR
                      2 = UNKNOWN_TYPE
                      3 = INCOMPLETE_FRAME
```

---

## 4. Control Signal Specification

### 4.1 ControlSignal

The primary reference produced by both the vision pipeline and the manual controller, consumed by `RobotSender` and encoded as `ControlRefPayload` on the wire.

| Field | Type | Range | Semantics |
|-------|------|-------|-----------|
| `angle_deg` | float32 | [-180, 180] | Direction the robot should move |
| `speed_ref` | float32 | [-1, 1] | Speed magnitude |

`ControlSignal(angle_deg=0.0, speed_ref=0.0)` is the canonical **stopped** state.

### 4.2 Wheel Power Mapping (Robot side)

Given `(angle_deg, speed_ref)`, compute raw wheel targets before rate limiting:

```
rad    = radians(angle_deg)
fwd    = speed_ref * cos(rad)
turn   = speed_ref * sin(rad)

left_target  = clamp(fwd - turn, -1.0, 1.0)
right_target = clamp(fwd + turn, -1.0, 1.0)
```

Lookup table:

| angle_deg | speed_ref | left | right | Motion |
|-----------|-----------|------|-------|--------|
| 0° | +1.0 | +1.0 | +1.0 | Straight forward |
| 0° | -1.0 | -1.0 | -1.0 | Straight backward |
| 0° | 0.0 | 0.0 | 0.0 | Stop |
| +90° | +1.0 | -1.0 | +1.0 | Pivot right |
| -90° | +1.0 | +1.0 | -1.0 | Pivot left |
| +45° | +1.0 | 0.0 | +1.0 | Curve right |
| -45° | +1.0 | +1.0 | 0.0 | Curve left |
| ±180° | +1.0 | -1.0 | -1.0 | Straight backward |

### 4.3 Rate Limiter

Applied on the robot at every control tick **after** `_computeTargets`:

```
MAX_DELTA_PER_TICK = 0.02   (tuning constant)
CONTROL_HZ         = 50     (tuning constant)

new_left  = current_left  + clamp(left_target  - current_left,  -MAX_DELTA, MAX_DELTA)
new_right = current_right + clamp(right_target - current_right, -MAX_DELTA, MAX_DELTA)
```

Full stop → full speed ramp: `1.0 / (0.02 × 50) = 1.0 s`.

---

## 5. `computer/types/` — Shared Interfaces

> **Rule:** This module contains only abstract interfaces and pure data types.
> No I/O, no threading, no business logic. Every concrete implementation
> lives inside its owning module (`communication/`, `vision/`, `manual/`).

### 5.1 `types/signals.py`

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Frame:
    frame_id:  int    # matches ImageChunkHeader.frame_id
    jpeg:      bytes  # complete assembled JPEG
    timestamp: float  # time.monotonic() at assembly completion

@dataclass(frozen=True)
class ControlSignal:
    angle_deg: float  # [-180.0, 180.0]
    speed_ref: float  # [-1.0, 1.0]

    @classmethod
    def stopped(cls) -> ControlSignal:
        return cls(angle_deg=0.0, speed_ref=0.0)
```

### 5.2 `types/detections.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class Detection:
    label:      str
    confidence: float                    # [0.0, 1.0]
    bbox:       tuple[int, int, int, int]  # (x, y, w, h) pixels

    @property
    def centre(self) -> tuple[float, float]:
        x, y, w, h = self.bbox
        return x + w / 2.0, y + h / 2.0

    @property
    def area(self) -> int:
        return self.bbox[2] * self.bbox[3]

@dataclass
class FrameResult:
    frame_id:   int
    detections: list[Detection]  = field(default_factory=list)
    annotated:  bytes | None     = None  # optional annotated JPEG for display
```

### 5.3 `types/observers.py`

Implements the Observer pattern that connects all modules. Each module that
**produces** a data type inherits the corresponding `Observable` mixin.
Modules that **consume** implement the matching `Observer` ABC.

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from .signals    import Frame, ControlSignal
from .detections import FrameResult

# ── Observers (consumers) ────────────────────────────────────────

class FrameObserver(ABC):
    @abstractmethod
    def on_frame(self, frame: Frame) -> None: ...

class ControlObserver(ABC):
    @abstractmethod
    def on_control(self, signal: ControlSignal) -> None: ...

class ResultObserver(ABC):
    @abstractmethod
    def on_result(self, result: FrameResult) -> None: ...

# ── Observables (producers — mixin) ──────────────────────────────

class FrameObservable:
    def __init__(self) -> None:
        self._frame_observers: list[FrameObserver] = []

    def add_frame_observer(self, obs: FrameObserver) -> None:
        self._frame_observers.append(obs)

    def _notify_frame(self, frame: Frame) -> None:
        for obs in self._frame_observers:
            obs.on_frame(frame)

class ControlObservable:
    def __init__(self) -> None:
        self._control_observers: list[ControlObserver] = []

    def add_control_observer(self, obs: ControlObserver) -> None:
        self._control_observers.append(obs)

    def _notify_control(self, signal: ControlSignal) -> None:
        for obs in self._control_observers:
            obs.on_control(signal)

class ResultObservable:
    def __init__(self) -> None:
        self._result_observers: list[ResultObserver] = []

    def add_result_observer(self, obs: ResultObserver) -> None:
        self._result_observers.append(obs)

    def _notify_result(self, result: FrameResult) -> None:
        for obs in self._result_observers:
            obs.on_result(result)
```

### 5.4 `types/transport.py`

```python
from __future__ import annotations
from abc import ABC, abstractmethod

class Transport(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send(self, data: bytes) -> None: ...

    @abstractmethod
    def receive_available(self, max_bytes: int = 4096) -> bytes:
        """Return available bytes without blocking. Return b'' if none."""
        ...

    @abstractmethod
    def is_connected(self) -> bool: ...
```

Concrete implementations (not in `types/`):

| Class | Location | Notes |
|-------|----------|-------|
| `SerialTransport` | `computer/communication/` | pyserial, non-blocking read |
| `RFCOMMTransport` | `computer/communication/` | Linux AF_BLUETOOTH socket |

---

## 6. `computer/communication/` — Network Layer

### 6.1 `communication/protocol.py`

Self-contained binary frame encoder and decoder. **No I/O, no threading.**

```python
# Message type namespaces
class CamMsg:
    IMAGE_CHUNK = 0x01
    ACK         = 0x02
    HEARTBEAT   = 0x03

class RobotMsg:
    CONTROL_REF = 0x01
    ACK         = 0x02
    HEARTBEAT   = 0x03

IMAGE_CHUNK_SIZE = 512  # bytes per chunk

# Payload dataclasses
@dataclass
class ImageChunkHeader:
    frame_id:     int
    chunk_idx:    int
    total_chunks: int
    total_size:   int
    SIZE: ClassVar[int] = 10
    _FMT: ClassVar[str] = '<HHHI'

    @classmethod
    def unpack(cls, data: bytes) -> ImageChunkHeader: ...
    def pack(self) -> bytes: ...

@dataclass
class ControlRefPayload:
    angle_deg: float
    speed_ref: float
    _FMT: ClassVar[str] = '<ff'

    def pack(self) -> bytes: ...

@dataclass
class AckPayload:
    acked_seq: int
    status:    int
    SIZE: ClassVar[int] = 3
    _FMT: ClassVar[str] = '<HB'

    def pack(self) -> bytes: ...
    @classmethod
    def unpack(cls, data: bytes) -> AckPayload: ...

# Decoded frame (output of FrameDecoder)
@dataclass
class DecodedFrame:
    msg_type: int
    seq_num:  int
    payload:  bytes
    crc_ok:   bool

class FrameEncoder:
    def build(self, msg_type: int, seq: int, payload: bytes) -> bytes: ...
    def build_image_chunk(self, seq: int, frame_id: int, chunk_idx: int,
                          total_chunks: int, total_size: int,
                          jpeg_data: bytes) -> bytes: ...
    def build_control_ref(self, seq: int, payload: ControlRefPayload) -> bytes: ...
    def build_ack(self, seq: int, acked_seq: int, status: int) -> bytes: ...
    def build_heartbeat(self, seq: int) -> bytes: ...

class FrameDecoder:
    """Streaming decoder: feed raw bytes, yields DecodedFrame objects."""
    def __init__(self) -> None: ...
    def feed(self, data: bytes) -> Generator[DecodedFrame, None, None]: ...
```

### 6.2 `communication/assembler.py`

Reassembles `IMAGE_CHUNK` messages into complete `Frame` objects.

```python
class ImageAssembler:
    def __init__(self, frame_timeout_s: float = 2.0) -> None: ...

    def on_chunk(self, header: ImageChunkHeader,
                 jpeg_chunk: bytes) -> Frame | None:
        """
        Returns a complete Frame when the last chunk of a frame arrives.
        Returns None for all intermediate chunks.
        Calls _evict_stale() on every call.
        """
        ...

    @property
    def pending_frame_count(self) -> int: ...
```

**Behavioral invariants:**
- Duplicate `chunk_idx` values for the same `frame_id` are silently ignored.
- Frames with all `total_chunks` received are assembled and removed from the buffer.
- Incomplete frames older than `frame_timeout_s` are evicted with a log warning.

### 6.3 `communication/cam_receiver.py`

Manages Link A. Receives frames from CAM, sends ACK after assembly.

```python
class CamReceiver(FrameObservable):
    def __init__(self,
                 transport: Transport,
                 reconnect: bool = True) -> None: ...

    def start(self) -> None: ...
    def stop(self)  -> None: ...
```

**Thread: `_rx_loop` (single daemon thread)**

```
loop:
  raw = transport.receive_available(4096)
  if not raw: sleep(5 ms); continue

  for frame in decoder.feed(raw):
    if not frame.crc_ok:
      send ACK(frame.seq_num, status=CRC_ERROR)
      continue

    if frame.msg_type == IMAGE_CHUNK:
      header, chunk = split(frame.payload)
      result = assembler.on_chunk(header, chunk)
      if result is not None:                  # full frame assembled
        _notify_frame(result)
        send ACK(frame.seq_num, status=OK)

    elif frame.msg_type == HEARTBEAT:
      record timestamp; reply HEARTBEAT if >1 s since last sent

    else:
      send ACK(frame.seq_num, status=UNKNOWN_TYPE)

  on ConnectionError + reconnect=True:
    log; wait 3 s; transport.connect()
```

**Heartbeat watchdog:** log warning if no HEARTBEAT received within 5 s.

### 6.4 `communication/robot_sender.py`

Manages Link B. Consumes `ControlSignal` events, sends `CONTROL_REF` frames.

```python
class RobotSender(ControlObserver):
    def __init__(self,
                 transport:   Transport,
                 max_rate_hz: float = 20.0,
                 reconnect:   bool  = True) -> None: ...

    def start(self) -> None: ...
    def stop(self)  -> None: ...

    # ControlObserver
    def on_control(self, signal: ControlSignal) -> None: ...
```

**`on_control` queuing:** enqueue into `queue.Queue(maxsize=1)`.
If full: drain the old entry first, then enqueue the new one (newest wins).

**Thread: `_tx_loop` (single daemon thread)**

```
loop:
  signal = queue.get(timeout = 1 / max_rate_hz)
  if signal is not None:
    encode + send CONTROL_REF
  else:
    send HEARTBEAT if >1 s since last sent

  on ConnectionError + reconnect=True:
    log; wait 3 s; transport.connect()
```

---

## 7. `computer/vision/` — Vision Pipeline

### 7.1 `vision/detectors/base.py`

```python
from abc import ABC, abstractmethod
import numpy as np
from computer.types.detections import Detection

class Detector(ABC):
    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[Detection]:
        """
        frame: BGR image as np.ndarray (H, W, 3), uint8.
        Returns zero or more Detection objects.
        """
        ...
```

### 7.2 `vision/detectors/colour_blob.py`

HSV colour range detector. Finds contours within the HSV range and returns
detections above `min_area`.

```python
class ColourBlobDetector(Detector):
    def __init__(self,
                 label:    str,
                 hsv_low:  tuple[int, int, int],
                 hsv_high: tuple[int, int, int],
                 min_area: int = 400) -> None: ...

    def detect(self, frame: np.ndarray) -> list[Detection]: ...
```

### 7.3 `vision/processor.py`

```python
class VisionProcessor(FrameObserver, ResultObservable):
    def __init__(self,
                 max_queue:    int  = 2,
                 show_preview: bool = False) -> None: ...

    def add_detector(self, detector: Detector) -> None: ...
    def start(self) -> None: ...
    def stop(self)  -> None: ...

    # FrameObserver
    def on_frame(self, frame: Frame) -> None: ...
```

**`on_frame` behavior:** enqueue into `queue.Queue(maxsize=max_queue)`.
If full: drop the oldest frame (get_nowait + put_nowait).

**Thread: `_worker_loop` (single daemon thread)**

```
loop:
  frame = queue.get(timeout=1.0)
  if frame is None: continue

  img = cv2.imdecode(np.frombuffer(frame.jpeg, np.uint8), cv2.IMREAD_COLOR)
  detections = []
  for detector in detectors:
    detections.extend(detector.detect(img))

  if show_preview:
    annotated = _draw_detections(img, detections)
    cv2.imshow("preview", annotated)
    cv2.waitKey(1)

  result = FrameResult(frame.frame_id, detections, annotated_jpeg_or_None)
  _notify_result(result)
```

### 7.4 `vision/strategy.py`

Converts `FrameResult` into `ControlSignal`. Default: blob follower.

```python
class BlobFollowerStrategy(ResultObserver, ControlObservable):
    def __init__(self,
                 frame_width: int   = 320,
                 steer_gain:  float = 90.0,
                 base_speed:  float = 0.5) -> None: ...

    # ResultObserver
    def on_result(self, result: FrameResult) -> None: ...
```

**`on_result` algorithm:**
```
if no detections:
    emit ControlSignal.stopped()
    return

target = detection with largest area
cx, _ = target.centre
error     = (cx - frame_width / 2) / (frame_width / 2)   # [-1.0, 1.0]
angle_deg = clamp(error * steer_gain, -180.0, 180.0)
emit ControlSignal(angle_deg=angle_deg, speed_ref=base_speed)
```

**Override this class** to implement alternative strategies (hand-sign activation, multi-target arbitration, etc.).

---

## 8. `computer/manual/` — Manual Control

### 8.1 `manual/keyboard.py`

```python
class KeyboardController(ControlObservable):
    def __init__(self, publish_rate_hz: float = 20.0) -> None: ...

    def start(self) -> None: ...    # starts pynput listener + publish loop thread
    def stop(self)  -> None: ...

    @property
    def is_esc_pressed(self) -> bool: ...
```

**Key → ControlSignal mapping:**

| Keys held | angle_deg | speed_ref |
|-----------|-----------|-----------|
| (none) | 0° | 0.0 (stop) |
| ↑ | 0° | +1.0 |
| ↓ | 180° | +1.0 |
| → | +90° | +1.0 |
| ← | -90° | +1.0 |
| ↑ + → | +45° | +1.0 |
| ↑ + ← | -45° | +1.0 |
| ↓ + → | +135° | +1.0 |
| ↓ + ← | -135° | +1.0 |

**Formula:**
```python
dy = (-1 if up else 0) + (1 if down  else 0)
dx = ( 1 if right else 0) + (-1 if left else 0)

if dy == 0 and dx == 0:
    signal = ControlSignal.stopped()
else:
    angle_deg = degrees(atan2(dx, -dy))
    signal = ControlSignal(angle_deg=angle_deg, speed_ref=1.0)
```

**Publish loop:** runs at `publish_rate_hz`, calls `_notify_control(signal)` every tick.

### 8.2 `manual/main.py`

```python
def main() -> None:
    # ── CONFIG ────────────────────────
    ROBOT_TRANSPORT = "serial"
    ROBOT_PORT      = "/tmp/robot-computer"
    # ──────────────────────────────────

    transport = SerialTransport(ROBOT_PORT)
    sender    = RobotSender(transport)
    keyboard  = KeyboardController()

    keyboard.add_control_observer(sender)

    def _shutdown(sig, frame):
        app.stop(); keyboard.stop(); sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    sender.start()
    keyboard.start()
    print("[MANUAL] Running — arrow keys to move, ESC or Ctrl+C to stop")

    while not keyboard.is_esc_pressed:
        time.sleep(0.1)

    _shutdown(None, None)
```

---

## 9. `computer/main.py` — Autonomous Vision Mode

```python
def main() -> None:
    # ── CONFIG ────────────────────────
    CAM_TRANSPORT   = "serial"
    CAM_PORT        = "/tmp/cam-computer"
    ROBOT_TRANSPORT = "serial"
    ROBOT_PORT      = "/tmp/robot-computer"
    SHOW_PREVIEW    = True
    # ──────────────────────────────────

    cam_transport   = SerialTransport(CAM_PORT)
    robot_transport = SerialTransport(ROBOT_PORT)

    cam_receiver = CamReceiver(cam_transport)
    processor    = VisionProcessor(show_preview=SHOW_PREVIEW)
    strategy     = BlobFollowerStrategy(frame_width=320, steer_gain=90.0, base_speed=0.5)
    robot_sender = RobotSender(robot_transport)

    processor.add_detector(ColourBlobDetector(
        label="target", hsv_low=(0, 120, 70), hsv_high=(10, 255, 255), min_area=400
    ))

    # Wire observer graph
    cam_receiver.add_frame_observer(processor)
    processor.add_result_observer(strategy)
    strategy.add_control_observer(robot_sender)

    def _shutdown(sig, frame):
        cam_receiver.stop(); processor.stop(); robot_sender.stop(); sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    robot_sender.start()
    processor.start()
    cam_receiver.start()
    print("[MAIN] Running — press Ctrl+C to stop")

    while True:
        time.sleep(5.0)
        # optional stats print here
```

---

## 10. `robot/` — ESP32 Motor Control Firmware

### 10.1 `robot/src/types/Protocol.h`

```cpp
#pragma once
#include <stdint.h>
#include <stddef.h>

namespace Protocol {

// Frame constants
constexpr uint8_t FRAME_START_1 = 0xCA;
constexpr uint8_t FRAME_START_2 = 0xFE;
constexpr uint8_t FRAME_END_1   = 0xED;
constexpr uint8_t FRAME_END_2   = 0xED;
constexpr size_t  OVERHEAD      = 13;   // 9 header + 4 footer (empty payload)

// Robot link message types
enum class MsgType : uint8_t {
    CONTROL_REF = 0x01,
    ACK         = 0x02,
    HEARTBEAT   = 0x03,
};

struct ControlRefPayload {
    float angle_deg;  // [-180.0, 180.0]
    float speed_ref;  // [-1.0, 1.0]
} __attribute__((packed));

struct AckPayload {
    uint16_t acked_seq;
    uint8_t  status;   // 0=OK  1=CRC_ERROR  2=UNKNOWN_TYPE  3=INCOMPLETE
} __attribute__((packed));

inline uint16_t crc16(const uint8_t* data, size_t len) {
    uint16_t crc = 0x0000;
    for (size_t i = 0; i < len; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (int j = 0; j < 8; ++j)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    return crc;
}

} // namespace Protocol
```

### 10.2 `robot/src/types/MotorTypes.h`

```cpp
#pragma once
#include <stdint.h>

struct WheelPins {
    uint8_t pwm;   // PWM output to H-bridge enable pin
    uint8_t dir;   // direction pin (HIGH = forward)
};

struct WheelSpeeds {
    float left;    // [-1.0, 1.0]
    float right;   // [-1.0, 1.0]
};
```

**Rationale for `robot/src/types/`:** both `RobotComm` and `WheelController`
depend on `ControlRefPayload` and `WheelSpeeds` respectively. A shared `types/`
header layer prevents either module from coupling to the other's header. See §12.

### 10.3 `robot/src/control/WheelController.h`

```cpp
#pragma once
#include <Arduino.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "../types/Protocol.h"
#include "../types/MotorTypes.h"

class WheelController {
public:
    static constexpr float MAX_DELTA_PER_TICK = 0.02f;
    static constexpr int   CONTROL_HZ         = 50;

    WheelController(WheelPins left, WheelPins right);
    void begin();                                           // configure LEDC + pins

    void setRef(const Protocol::ControlRefPayload& ref);   // mutex-protected write
    void update();                                          // call at CONTROL_HZ
    void emergencyStop();                                   // immediate stop, no slew

    float currentLeft()  const;
    float currentRight() const;

private:
    WheelSpeeds _computeTargets(float angle_deg, float speed_ref) const;
    void        _driveMotor(const WheelPins& pins, uint8_t channel, float power);
    static float _clamp(float v, float lo, float hi);

    SemaphoreHandle_t         _ref_mutex;
    Protocol::ControlRefPayload _ref { 0.0f, 0.0f };

    float _current_left  { 0.0f };
    float _current_right { 0.0f };

    WheelPins _left;
    WheelPins _right;

    static constexpr uint8_t LEFT_CHANNEL  = 2;
    static constexpr uint8_t RIGHT_CHANNEL = 3;
};
```

**`_computeTargets` implementation:**
```cpp
WheelSpeeds WheelController::_computeTargets(float angle_deg, float speed_ref) const {
    float rad  = angle_deg * M_PI / 180.0f;
    float fwd  = speed_ref * cosf(rad);
    float turn = speed_ref * sinf(rad);
    return { _clamp(fwd - turn, -1.0f, 1.0f),
             _clamp(fwd + turn, -1.0f, 1.0f) };
}
```

**`update` implementation:**
```cpp
void WheelController::update() {
    Protocol::ControlRefPayload ref;
    xSemaphoreTake(_ref_mutex, portMAX_DELAY);
    ref = _ref;
    xSemaphoreGive(_ref_mutex);

    WheelSpeeds targets = _computeTargets(ref.angle_deg, ref.speed_ref);

    auto slew = [](float cur, float tgt) -> float {
        float d = tgt - cur;
        d = d > MAX_DELTA_PER_TICK ? MAX_DELTA_PER_TICK :
            d < -MAX_DELTA_PER_TICK ? -MAX_DELTA_PER_TICK : d;
        return cur + d;
    };

    _current_left  = slew(_current_left,  targets.left);
    _current_right = slew(_current_right, targets.right);

    _driveMotor(_left,  LEFT_CHANNEL,  _current_left);
    _driveMotor(_right, RIGHT_CHANNEL, _current_right);
}
```

### 10.4 `robot/src/communication/RobotComm.h`

```cpp
#pragma once
#include <BluetoothSerial.h>
#include "../control/WheelController.h"

class RobotComm {
public:
    RobotComm(WheelController& wheel, const char* bt_name = "RobotESP32");
    void begin();   // init BT + start FreeRTOS tasks

private:
    static void _btTask(void* arg);       // core 1, priority 5
    static void _controlTask(void* arg);  // core 1, priority 4
    static void _watchdogTask(void* arg); // core 1, priority 3

    WheelController& _wheel;
    BluetoothSerial  _bt;
    const char*      _bt_name;

    volatile uint32_t _last_rx_ms { 0 };   // set by _btTask, read by _watchdogTask
};
```

**FreeRTOS task table:**

| Task | Core | Priority | Stack | Function |
|------|------|----------|-------|----------|
| `_btTask` | 1 | 5 | 4096 B | BT RX → decode → `wheel.setRef()` |
| `_controlTask` | 1 | 4 | 2048 B | `wheel.update()` at CONTROL_HZ |
| `_watchdogTask` | 1 | 3 | 2048 B | `emergencyStop()` if no RX within 3 s |

**`_btTask` behavior:**
```
loop:
  read available bytes into ring buffer
  for each decoded frame:
    if crc_ok and msg_type == CONTROL_REF:
      wheel.setRef(payload)
      _last_rx_ms = millis()
      send ACK(seq, OK)
    elif msg_type == HEARTBEAT:
      _last_rx_ms = millis()
      send HEARTBEAT
    elif crc error:
      send ACK(seq, CRC_ERROR)
    else:
      send ACK(seq, UNKNOWN_TYPE)
```

---

## 11. `cam/` — ESP32-CAM Firmware

### 11.1 `cam/src/types/Protocol.h`

Copy of `robot/src/types/Protocol.h` with **CAM link message types:**

```cpp
enum class MsgType : uint8_t {
    IMAGE_CHUNK = 0x01,
    ACK         = 0x02,
    HEARTBEAT   = 0x03,
};

struct ImageChunkHeader {
    uint16_t frame_id;
    uint16_t chunk_idx;
    uint16_t total_chunks;
    uint32_t total_size;
} __attribute__((packed));
```

(`AckPayload`, frame constants, `crc16` identical to robot version.)

> **Do not share a single `Protocol.h` between `cam/` and `robot/` at the build
> level** — they are separate PlatformIO projects with independent build graphs.
> Keep the two copies in sync manually whenever the wire format changes.

### 11.2 `cam/src/communication/CamComm.h`

```cpp
#pragma once
#include <BluetoothSerial.h>
#include "esp_camera.h"

class CamComm {
public:
    CamComm(float target_fps = 6.0f, const char* bt_name = "RobotCAM");
    void begin();   // init camera + BT + start FreeRTOS tasks

private:
    static void _cameraTask(void* arg);  // core 0, priority 3
    static void _rxTask(void* arg);      // core 1, priority 4

    BluetoothSerial  _bt;
    const char*      _bt_name;
    float            _target_fps;
    uint16_t         _frame_id     { 0 };
    volatile bool    _bt_connected { false };
};
```

**FreeRTOS task table:**

| Task | Core | Priority | Stack | Function |
|------|------|----------|-------|----------|
| `_cameraTask` | 0 | 3 | 8192 B | Capture JPEG → chunk → send |
| `_rxTask` | 1 | 4 | 4096 B | Receive ACK + HEARTBEAT; watchdog |

**`_cameraTask` behavior:**
```
loop:
  if not _bt_connected: vTaskDelay(100 ms); continue

  jpeg = esp_camera_fb_get()
  total_chunks = ceil(jpeg.len / 512)
  for i in 0..total_chunks:
    build IMAGE_CHUNK(seq++, frame_id, i, total_chunks, jpeg.len, data[i*512:(i+1)*512])
    _bt.write(frame)
    vTaskDelay(0)   // yield

  _frame_id = (_frame_id + 1) & 0xFFFF
  esp_camera_fb_return(jpeg)
  delay to maintain target_fps
```

**`_rxTask` behavior:**
```
loop:
  read available bytes
  for each decoded frame:
    if msg_type == ACK:
      log if status != OK
    elif msg_type == HEARTBEAT:
      _bt_connected = true; _last_hb_ms = millis(); send HEARTBEAT
    elif crc error: ignore (no ACK back to computer on CAM link)

  if millis() - _last_hb_ms > 5000:
    _bt_connected = false   // will pause camera task
```

---

## 12. Why `robot/src/types/` Is Needed

Without a shared types directory, two problems arise:

1. **Coupling**: `RobotComm.cpp` calls `wheel.setRef(payload)`, so it must know
   the `ControlRefPayload` type. If this struct lives in `WheelController.h`,
   then `RobotComm` imports a motor-control header just for a data type —
   tight coupling between unrelated concerns.

2. **Direction**: `WheelController` should not know about the serial protocol.
   Moving `ControlRefPayload` out of `WheelController.h` into `types/Protocol.h`
   gives both modules a shared vocabulary without either owning it.

`cam/src/types/` provides the same benefit on the CAM side (`CamComm` needs
`ImageChunkHeader` independently of any other module).

---

## 13. Development Phases

### Phase 1 — Manual mode, no hardware (socat virtual ports)

```bash
# Terminal 1 — CAM virtual port pair
socat pty,raw,echo=0,link=/tmp/cam-emulator pty,raw,echo=0,link=/tmp/cam-computer

# Terminal 2 — Robot virtual port pair
socat pty,raw,echo=0,link=/tmp/robot-emulator pty,raw,echo=0,link=/tmp/robot-computer

# Terminal 3 — Manual computer app
python -m computer.manual.main
```

Implement a minimal CAM emulator (sends synthetic IMAGE_CHUNK frames) and a
minimal Robot emulator (receives CONTROL_REF, prints to stdout) as standalone
Python scripts.

### Phase 2 — Physical robot, manual control

Flash `robot/`. Pair via Bluetooth. Edit `ROBOT_PORT` in `computer/manual/main.py`.
Test smooth motion ramp-up and emergency stop on BT disconnect.

### Phase 3 — Physical robot + CAM, autonomous

Flash both `robot/` and `cam/`. Edit ports in `computer/main.py`.
Tune `ColourBlobDetector` HSV ranges for target. Add or replace detectors.

---

## 14. Build Configuration

### `pyproject.toml`

```toml
[build-system]
requires      = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name            = "robot-vision"
version         = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "numpy>=1.24",
    "opencv-python>=4.8",
    "pyserial>=3.5",
    "pynput>=1.7",
]

[project.scripts]
robot-vision  = "computer.main:main"
robot-manual  = "computer.manual.main:main"

[tool.setuptools.packages.find]
where   = ["."]
include = ["computer*"]
```

### `robot/platformio.ini`

```ini
[env:esp32]
platform      = espressif32
board         = esp32dev
framework     = arduino
monitor_speed = 115200
build_src_filter = +<*> -<../cam/>
```

### `cam/platformio.ini`

```ini
[env:esp32cam]
platform      = espressif32
board         = esp32cam
framework     = arduino
monitor_speed = 115200
build_src_filter = +<*> -<../robot/>
```
