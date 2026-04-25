# Robot Communication Monorepo

End-to-end system for an autonomous cargo-carrying robot controlled by computer vision.  
The repository hosts every software layer — firmware, shared protocol, host application, vision pipeline, and hardware emulator — as first-class modules in a single codebase.

---

## Repository structure

```
.
├── firmware/                  ESP32-CAM firmware (C++ / PlatformIO)
│   ├── platformio.ini
│   └── src/
│       ├── Protocol.h         Binary protocol constants and CRC
│       ├── BluetoothComm.h/.cpp   BT Classic SPP transport + RX state machine
│       ├── CameraModule.h/.cpp    ESP32-CAM wrapper (AI Thinker pins)
│       ├── WheelController.h/.cpp Direction-ref input + smooth-motion control loop
│       ├── RobotComm.h/.cpp   FreeRTOS task orchestrator
│       └── main.cpp           Entry point
│
├── communication/             Shared Python package — protocol + transport
│   ├── __init__.py
│   ├── protocol.py            FrameEncoder, FrameDecoder, all payload types, CRC
│   └── transport.py           BluetoothTransport ABC → RFCOMMTransport / SerialTransport
│
├── vision/                    Computer vision module (independent developer)
│   ├── __init__.py
│   ├── results.py             Detection, FrameResult dataclasses
│   ├── processor.py           Async ImageProcessor (queue + worker thread)
│   └── detectors/
│       ├── __init__.py
│       ├── base.py            Detector ABC
│       └── colour_blob.py     ColourBlobDetector (HSV range + contours)
│
├── computer/                  Host application
│   ├── __init__.py
│   ├── assembler.py           ImageAssembler (chunk reassembly)
│   ├── controller.py          RobotController (vision → DirectionCommand)
│   ├── app.py                 CommunicationApp (RX/TX thread orchestrator)
│   └── main.py                Entry point
│
├── emulator/                  Git submodule → github.com/Cerne17/oop-emulator
│   └── src/                   Managed entirely by the submodule's own repo
│
├── pyproject.toml             Root package config — one install for all modules
├── requirements.txt           Unified Python dependencies
├── EMULATOR_SPEC.md           Emulator design specification
└── README.md
```

---

## Module overview

### `communication/` — shared protocol

The binary frame format used by every layer. Both the computer app and the emulator import from here (the emulator also ships its own copy for standalone use).

```python
from communication.protocol import FrameEncoder, DirectionRefPayload
from communication.transport import SerialTransport
```

### `vision/` — computer vision pipeline

Maintained by the CV developer independently. The host app imports `ImageProcessor` and registers detectors. The `Detector` base class makes it easy to swap or stack detectors without touching orchestration logic.

```python
from vision import ImageProcessor
from vision.detectors import ColourBlobDetector  # Phase 1/2 placeholder
# Phase 3: add hand-sign and subject-tracking detectors here
```

### `computer/` — host application

Wires transport → assembler → vision → controller → transport in two threads (RX and TX). Decoupled from vision: the controller only receives `FrameResult` and emits `DirectionCommand`.

```python
# run from repo root:
python -m computer.main
```

### `emulator/` — robot emulator (git submodule)

A separate project at [github.com/Cerne17/oop-emulator](https://github.com/Cerne17/oop-emulator), included here as a submodule. It replaces the physical robot during Phases 1 and 2: streams synthetic JPEG frames over a virtual serial port and reads arrow keys to generate direction-reference signals.

See [EMULATOR_SPEC.md](EMULATOR_SPEC.md) for the wire-level contract this repo defines and the submodule implements. All changes to the emulator source go to that repo.

```bash
cd emulator
python src/main.py --mode blob --fps 6
```

### `firmware/` — ESP32-CAM firmware

PlatformIO project. Flash with `pio run --target upload` from `firmware/`.

---

## Data flow

```
┌──────────────────────────────────────────────────────────────────┐
│                     ESP32-CAM  (firmware/)                       │
│                                                                  │
│  CameraModule ──► RobotComm ──► BluetoothComm ──► BT SPP link   │
│  WheelController ◄── (direction ref) ──────────────────────────  │
│      └── 50 Hz control loop (rate-limited, smooth motion)        │
└──────────────────────────────────────────────────────────────────┘
                               ▲  ▼  Bluetooth Classic SPP
┌──────────────────────────────────────────────────────────────────┐
│                     Computer  (computer/)                        │
│                                                                  │
│  Transport → FrameDecoder → ImageAssembler → ImageProcessor      │
│                                                   │ (vision/)    │
│                                            RobotController       │
│                                                   │              │
│  Transport ← FrameEncoder ← DIRECTION_REF ◄───────┘             │
└──────────────────────────────────────────────────────────────────┘
```

**What travels over the link:**

| Direction | Message | Rate |
|-----------|---------|------|
| ESP32 → PC | `IMAGE_CHUNK` (512-byte JPEG chunks) | ~6–10 FPS |
| PC → ESP32 | `DIRECTION_REF` (angle_deg + stop flag) | up to 20 Hz |
| Both | `HEARTBEAT` | 1 Hz |
| Both | `ACK` | on error |

---

## Binary protocol (quick reference)

```
[0xCA][0xFE]  start
[TYPE]        1 byte  — 0x01 IMAGE_CHUNK | 0x02 DIRECTION_REF | 0x03 ACK | 0x04 HEARTBEAT
[SEQ]         2 bytes LE uint16
[LEN]         4 bytes LE uint32
[PAYLOAD]     variable
[CRC16]       2 bytes LE — CRC-16/CCITT over TYPE+SEQ+LEN+PAYLOAD
[0xED][0xED]  end
```

Full specification: [EMULATOR_SPEC.md §3](EMULATOR_SPEC.md).

---

## Development roadmap

| Phase | Input | Robot | Goal |
|-------|-------|-------|------|
| **1** | Arrow keys (emulator) | Emulated | Validate protocol + control logic without hardware |
| **2** | Arrow keys (computer app) | Physical ESP32 | Validate over real Bluetooth |
| **3** | Computer vision (hand signs + subject tracking) | Physical ESP32 | Full autonomous operation |

---

## Getting started

### Python setup

```bash
# From the repository root — installs communication, vision, computer + CLI script
pip install -e .
```

### Phase 1 — emulated end-to-end test

**Terminal 1** — virtual serial link:
```bash
socat -d -d \
  pty,raw,echo=0,link=/tmp/robot-emulator \
  pty,raw,echo=0,link=/tmp/robot-computer
```

**Terminal 2** — emulator (arrow keys → synthetic camera frames):
```bash
cd emulator
python src/main.py --mode blob --fps 6
```

**Terminal 3** — host application:
```bash
# edit computer/main.py: TRANSPORT="serial", SERIAL_PORT="/tmp/robot-computer"
python -m computer.main
# or: robot-computer
```

### Phase 2 — physical robot

Pair the ESP32 in **System Settings → Bluetooth** (macOS), then in `computer/main.py`:
```python
TRANSPORT   = "serial"
SERIAL_PORT = "/dev/cu.RobotESP32-SerialPort"
```

Flash the firmware:
```bash
cd firmware
pio run --target upload
pio device monitor
```

### Phase 3 — computer vision

Add detectors in `vision/detectors/`:
```python
# vision/detectors/hand_sign.py
from .base import Detector

class HandSignDetector(Detector):
    def detect(self, frame):
        # ... your model inference ...
        return [Detection("activate", confidence, bbox)]
```

Register in `computer/main.py`:
```python
from vision.detectors.hand_sign import HandSignDetector
processor.add_detector(HandSignDetector(...))
```

---

## Git cleanup

The repository previously had a flat `computer/src/` layout and `esp32/` directory. The new layout replaces them. Remove the stale files:

```bash
# Remove old directories (content is now in the package layout)
git rm -r esp32/
git rm -r computer/src/ computer/requirements.txt

git commit -m "refactor: monorepo — communication, vision, computer, firmware packages"
```

The `emulator` submodule and `.gitmodules` are **unchanged** — keep them as-is.
