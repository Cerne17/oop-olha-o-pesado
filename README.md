# OOP Communication Module — ESP32 ↔ Computer over Bluetooth

Real-time bidirectional communication layer between a computer and an ESP32-CAM robot.  
The computer receives a live camera stream and wheel telemetry; the ESP32 receives wheel power commands computed from a CV pipeline running on the host.

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        ESP32-CAM (robot)                        │
│                                                                 │
│  CameraModule ──► RobotComm ──► BluetoothComm ──► BT Classic   │
│  WheelController ◄──────────────────────────────── (SPP)        │
└─────────────────────────────────────────────────────────────────┘
                              ▲  ▼
                       Bluetooth Classic SPP
                              ▲  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Computer (host)                          │
│                                                                 │
│  Transport ──► CommunicationModule ──► ImageAssembler           │
│                       │                      │                  │
│                       │               ImageProcessor (CV)       │
│                       │                      │                  │
│                       └──── RobotController ◄┘                  │
│                                   │                             │
│                        WheelControl frames ──► Transport        │
└─────────────────────────────────────────────────────────────────┘
```

### Data flows

| Direction | Data | Rate |
|-----------|------|------|
| ESP32 → PC | JPEG image chunks | ~6–10 FPS (configurable) |
| ESP32 → PC | Wheel telemetry (left RPM, right RPM, speed) | 10 Hz |
| ESP32 → PC | Heartbeat | 1 Hz |
| PC → ESP32 | Wheel power commands (left, right ∈ [-1.0, 1.0]) | up to 20 Hz |

---

## Repository structure

```
oop-communication-module/
├── esp32/                         C++ firmware (PlatformIO / Arduino)
│   ├── platformio.ini
│   └── src/
│       ├── Protocol.h             Binary protocol — constants, packed structs, CRC-16
│       ├── BluetoothComm.h/.cpp   Bluetooth Classic SPP transport + RX state machine
│       ├── CameraModule.h/.cpp    ESP32-CAM wrapper (AI Thinker pin map)
│       ├── WheelController.h/.cpp H-bridge PWM driver + encoder ISR + RPM/speed calc
│       ├── RobotComm.h/.cpp       Top-level orchestrator — spawns 3 FreeRTOS tasks
│       └── main.cpp               Entry point — configure pins and parameters here
│
└── computer/                      Python host application
    ├── requirements.txt
    └── src/
        ├── protocol.py            Python mirror of Protocol.h (FrameEncoder / FrameDecoder)
        ├── transport.py           BluetoothTransport ABC → RFCOMMTransport / SerialTransport
        ├── image_assembler.py     Chunk reassembly with stale-frame eviction
        ├── image_processor.py     Async OpenCV pipeline + ColourBlobDetector example
        ├── robot_controller.py    CV results → wheel commands (proportional follower)
        ├── communication_module.py RX/TX threads, wires all components together
        └── main.py                Entry point — edit CONFIG block and run
```

---

## Binary protocol

All multi-byte fields are **little-endian**.

```
┌──────────┬──────────┬──────────┬───────────────┬──────────────────┬──────────┬──────────┬──────────┐
│  0xCA    │  0xFE    │ MSG_TYPE │    SEQ_NUM    │   PAYLOAD_LEN    │ PAYLOAD… │  CRC16   │ 0xED 0xED│
│ (start)  │          │ (1 byte) │  (2 bytes LE) │   (4 bytes LE)   │          │ (2 bytes)│  (end)   │
└──────────┴──────────┴──────────┴───────────────┴──────────────────┴──────────┴──────────┴──────────┘
```

**CRC** covers `MSG_TYPE + SEQ_NUM + PAYLOAD_LEN + PAYLOAD` using CRC-16/CCITT (polynomial `0x1021`, init `0x0000`). The same function is implemented in both `Protocol.h` and `protocol.py`.

### Message types

| Value | Name | Direction | Payload |
|-------|------|-----------|---------|
| `0x01` | `IMAGE_CHUNK` | ESP32 → PC | `ImageChunkHeader` (10 bytes) + JPEG bytes |
| `0x02` | `TELEMETRY` | ESP32 → PC | `left_rpm`, `right_rpm`, `speed_mps`, `timestamp_ms` (16 bytes) |
| `0x03` | `WHEEL_CONTROL` | PC → ESP32 | `left_power`, `right_power` (8 bytes, floats) |
| `0x04` | `ACK` | bidirectional | `acked_seq` (uint16) + `status` (uint8) |
| `0x05` | `HEARTBEAT` | bidirectional | empty |

### Image chunking

JPEG frames are split into **512-byte chunks**. Each chunk carries an `ImageChunkHeader`:

```
frame_id      uint16  — monotonically increasing frame identifier
chunk_idx     uint16  — 0-based index of this chunk
total_chunks  uint16  — total number of chunks in this frame
total_size    uint32  — full JPEG size in bytes
```

`ImageAssembler` on the host collects chunks by `frame_id`, detects completion, and evicts incomplete frames older than 2 seconds.

---

## ESP32 side

### Classes

| Class | File | Responsibility |
|-------|------|----------------|
| `BluetoothComm` | `BluetoothComm.h/.cpp` | Wraps `BluetoothSerial`. Encodes outgoing frames, runs a byte-level RX state machine, dispatches decoded messages to registered callbacks. Thread-safe TX via FreeRTOS mutex. |
| `CameraModule` | `CameraModule.h/.cpp` | Initialises the OV2640 sensor via `esp_camera_init()`. Exposes `capture()` / `releaseFrame()`. Supports runtime resolution and quality changes. |
| `WheelController` | `WheelController.h/.cpp` | Controls two wheels via LEDC PWM + direction pins. Counts encoder pulses in ISRs and computes RPM and linear speed on each `update()` call. Accepts `WheelControlPayload` directly. |
| `RobotComm` | `RobotComm.h/.cpp` | Top-level orchestrator. Spawns three FreeRTOS tasks: BT polling + heartbeat, camera capture + streaming, telemetry transmission. Wires `WHEEL_CONTROL` frames to `WheelController`. |

### FreeRTOS tasks

| Task | Core | Priority | Interval |
|------|------|----------|----------|
| `bt_task` — polls BT, sends heartbeats, stops wheels on link loss | 1 | 5 | 5 ms |
| `cam_task` — captures JPEG, chunks and transmits | 0 | 3 | configurable (default 150 ms) |
| `telem_task` — calls `wheels.update()`, sends `TELEMETRY` | 1 | 2 | configurable (default 100 ms) |

### Hardware configuration

Edit `buildConfig()` in `main.cpp`:

```cpp
cfg.left_wheel  = { .pwm = 14, .dir = 12, .enc_a = 13 };
cfg.right_wheel = { .pwm = 15, .dir =  2, .enc_a =  4 };
cfg.wheelbase_m            = 0.20f;
cfg.wheel_circumference_m  = 0.20f;
cfg.encoder_pulses_per_rev = 20;
```

The camera uses the standard **AI Thinker ESP32-CAM** pin map, defined in `CameraModule.h`.  
Resolution defaults to `FRAMESIZE_QVGA` (320×240). Lower resolutions increase frame rate; higher ones increase detail at the cost of bandwidth.

### Building & flashing

Requires [PlatformIO](https://platformio.org/).

```bash
cd esp32
pio run --target upload
pio device monitor     # 115200 baud
```

---

## Computer side

### Classes

| Class | File | Responsibility |
|-------|------|----------------|
| `FrameEncoder` | `protocol.py` | Stateful encoder — assigns sequence numbers and builds complete binary frames. |
| `FrameDecoder` | `protocol.py` | Streaming decoder — feed raw bytes from the transport; returns `DecodedFrame` objects. Handles fragmentation and CRC errors. |
| `BluetoothTransport` | `transport.py` | Abstract base class defining `connect`, `disconnect`, `send`, `receive`, `is_connected`. |
| `RFCOMMTransport` | `transport.py` | Linux back-end using raw `AF_BLUETOOTH / BTPROTO_RFCOMM` sockets. No extra libraries needed. |
| `SerialTransport` | `transport.py` | macOS / cross-platform back-end using `pyserial` over the paired BT serial port. |
| `ImageAssembler` | `image_assembler.py` | Buffers incoming image chunks per `frame_id`; emits a complete JPEG `bytes` object when all chunks arrive. Evicts stale incomplete frames. |
| `ImageProcessor` | `image_processor.py` | Async OpenCV pipeline. Frames are queued and processed in a background thread. Detectors are plug-in; results are delivered via callback. |
| `ColourBlobDetector` | `image_processor.py` | Example `Detector` subclass — finds colour blobs in HSV space using `cv2.inRange` + contour detection. |
| `RobotController` | `robot_controller.py` | Converts `FrameResult` objects into `WheelCommand` objects. Default strategy: proportional steering toward the largest detected blob. |
| `CommunicationModule` | `communication_module.py` | Wires transport ↔ decoder ↔ assembler ↔ processor ↔ controller. Runs RX and TX in dedicated threads with automatic reconnect. |

### Running on macOS

1. Pair the ESP32 in **System Settings → Bluetooth**. macOS creates a port like `/dev/cu.RobotESP32-SerialPort`.
2. Edit `computer/src/main.py`:
   ```python
   TRANSPORT   = "serial"
   SERIAL_PORT = "/dev/cu.RobotESP32-SerialPort"   # adjust to your port name
   ```
3. Install dependencies and run:
   ```bash
   pip install -r computer/requirements.txt
   python computer/src/main.py
   ```

### Running on Linux

No pairing needed — use RFCOMM sockets directly:

```bash
# Find the ESP32's MAC address (one-time)
hcitool scan

# Edit main.py
TRANSPORT = "rfcomm"
BT_MAC    = "AA:BB:CC:DD:EE:FF"
```

Then run as above. If you prefer the serial back-end on Linux:
```bash
sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF 1
# port is now /dev/rfcomm0
```

### Extending the CV pipeline

Add a custom detector by subclassing `Detector` in `image_processor.py`:

```python
from image_processor import Detector, Detection
import cv2, numpy as np

class MyDetector(Detector):
    def detect(self, frame: np.ndarray) -> list[Detection]:
        # ... your OpenCV logic ...
        return [Detection("my_label", confidence, (x, y, w, h))]

processor.add_detector(MyDetector())
```

Override the control strategy by subclassing `RobotController` and implementing `_compute_command()`:

```python
from robot_controller import RobotController, WheelCommand
from image_processor import FrameResult

class LineFollower(RobotController):
    def _compute_command(self, result: FrameResult) -> WheelCommand:
        # your line-following logic
        return WheelCommand(left=0.4, right=0.4)
```

---

## Dependencies

### ESP32 (bundled with Espressif Arduino core — no extra install)
- `BluetoothSerial`
- `esp_camera`
- FreeRTOS (built-in)

### Computer
```
numpy>=1.24
opencv-python>=4.8
pyserial>=3.5          # for SerialTransport (macOS / Linux rfcomm)
```

---

## Tuning tips

| Goal | Parameter |
|------|-----------|
| Higher frame rate | Lower `camera_interval_ms` + smaller resolution (`FRAMESIZE_QQVGA`) |
| Better image quality | Lower `camera_quality` (0 = best, 63 = worst) + larger resolution |
| Faster control response | Lower `send_interval_s` in `CommunicationModule` |
| Reduce BT congestion | Increase `IMAGE_CHUNK_DATA_SIZE` (up to ~1024 bytes) |
| Wheel speed accuracy | Increase `encoder_pulses_per_rev` to match your encoder spec |
