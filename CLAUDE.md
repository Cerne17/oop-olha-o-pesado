# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

End-to-end autonomous cargo-carrying robot with computer vision. Three hardware components communicate over a shared binary wire protocol:

- **ESP32 Robot board** (`robot/`) — differential-drive motor control (C++/PlatformIO)
- **ESP32-CAM board** (`cam/`) — JPEG frame streaming (C++/PlatformIO)
- **Host computer** (`computer/`) — vision pipeline + control logic (Python ≥3.11)
- **Emulator** (`emulator/`) — TCP-based software simulation for Phase 1 (no hardware needed)

Three development phases: Phase 1 = manual control via TCP emulator, Phase 2 = manual control over physical BT, Phase 3 = autonomous vision-guided control.

## Commands

### Python Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Running (all phases)
```bash
bash scripts/run.sh 1   # Phase 1: manual + TCP emulator
bash scripts/run.sh 2   # Phase 2: manual + physical robot BT
bash scripts/run.sh 3   # Phase 3: autonomous + physical robot + CAM BT
```

### Firmware (PlatformIO)
```bash
cd robot && pio run --target upload   # flash robot board
cd cam && pio run --target upload     # flash CAM board
```

There is no automated test suite — testing is done via the emulator (Phase 1) for end-to-end validation.

## Architecture

### Data Flow (Phase 3)
```
ESP32-CAM → [Link A: BT/Serial] → CamReceiver → ImageAssembler → VisionProcessor
                                                                        ↓
ESP32 Robot ← [Link B: BT/Serial] ← RobotSender ← BlobFollowerStrategy ←
```

**Link A** carries IMAGE_CHUNK frames (CAM → Computer). **Link B** carries CONTROL_REF frames (Computer → Robot).

### Wire Protocol (same framing on both links)
```
[0xCA][0xFE] [TYPE:1B] [SEQ:2B LE] [LEN:4B LE] [PAYLOAD] [CRC16:2B LE] [0xED][0xED]
```
- Link A message types: `IMAGE_CHUNK` (0x01), `ACK` (0x02), `HEARTBEAT` (0x03)
- Link B message types: `CONTROL_REF` (0x01), `ACK` (0x02), `HEARTBEAT` (0x03)
- CRC: CRC-16/CCITT XModem over TYPE+SEQ+LEN+PAYLOAD
- Heartbeat sent every 1 s; watchdog timeout = 5 s

When adding a new message type, run `/sync-message-type` — it covers all the touch points across firmware, computer, and emulator simultaneously.

### Threading Model
Each major component owns its thread:
- `cam-rx` — bytes → `FrameDecoder` (state machine) → `ImageAssembler` → notify Frame
- `vision-worker` — queue-fed frame processing → `FrameResult`
- `robot-tx` — newest-wins queue (maxsize=1); 20 Hz send rate, 1 Hz heartbeat fallback
- `keyboard-pub` — 20 Hz key polling (manual phases only)

Key invariants: main thread never blocks on I/O; newest-wins queues drop stale commands; graceful shutdown via stop event + 3 s join timeout.

### Observer Pattern
Modules are decoupled via typed observer/observable pairs in `computer/types/`:
- `FrameObserver/Observable` — CamReceiver → VisionProcessor
- `ResultObserver/Observable` — VisionProcessor → BlobFollowerStrategy
- `ControlObserver/Observable` — Strategy/KeyboardController → RobotSender

### Key Files
| File | Role |
|------|------|
| `computer/main.py` | Phase router and component factory |
| `computer/types/` | Shared signal contracts (Frame, ControlSignal, FrameResult) |
| `computer/communication/protocol.py` | Binary codec (pure, no I/O) |
| `computer/communication/cam_receiver.py` | Link A orchestrator |
| `computer/communication/robot_sender.py` | Link B TX thread |
| `emulator/src/robot_emulator.py` | Emulator main coordinator |
| `SPEC.md` | Full system spec (wire format, FSMs, algorithms) |
| `RUNNING.md` | Step-by-step execution guides for all phases |
| `FIRMWARE.md` | Hardware wiring and flashing instructions |
| `THREADS.md` | Threading model documentation |

### Unimplemented Stubs
`VisionProcessor._worker_loop()` and `BlobFollowerStrategy.on_result()` are `NotImplementedError` — Phase 3 vision logic is not yet implemented.

## Custom Skills

Project skills live in `.claude/skills/` and are auto-discovered by Claude Code. Use them when:
- `/sync-message-type` — adding a new wire message type (cross-cutting, touches Python + C++ + emulator)
- `/add-message-type` — adding a new wire message on one link only
- `/debug-computer-comm` — frames not arriving, CRC errors, heartbeat timeouts
- `/implement-transport` — adding a new link type (WebSocket, UDP, …)
- `/use-udp-transport` — switching Link B to UDP over WiFi (computer config + ESP32 firmware port)
- `/debug-udp` — UDP-specific issues: no datagrams, CRC errors, watchdog over WiFi
- `/implement-detector` — writing a new `Detector` subclass
- `/implement-strategy` — writing a new `ControlStrategy`
- `/debug-robot-comm` — BT pairing failures, watchdog triggers, wrong wheel behaviour
- `/add-motion-mode` — adding a new drive mode
- `/debug-cam-comm` — camera init failure, frames not streaming
- `/debug-emulator` — TCP connection issues, threads dying, wrong wheel output
- `/extend-emulator` — adding battery simulation, encoder feedback, or new mock messages
- `/debug-upload` — `Failed to connect to ESP32`, bootloader mode
- `/debug-serial` — garbage output, wrong baud rate, permission errors
- `/debug-cam-init` — `camera init failed`, ribbon cable, streaming issues
- `/debug-bluetooth` — BT device not found, `rfcomm bind`, wrong BT name
- `/configure-firmware` — changing motor pins, BT names, frame rate, JPEG quality
