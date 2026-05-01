# Robot Vision System

End-to-end system for an autonomous cargo-carrying robot controlled by computer vision.
The repository hosts every software layer — firmware for two ESP32 boards, a Python host
application, a vision pipeline, and a software emulator — as first-class modules in a
single codebase.

For step-by-step setup and run instructions see **[RUNNING.md](RUNNING.md)**.
For firmware wiring, drivers, and flashing see **[FIRMWARE.md](FIRMWARE.md)**.
For the full design specification see **[SPEC.md](SPEC.md)**.
For the threading model see **[THREADS.md](THREADS.md)**.
For agentic development skills see **`.claude/skills/`** (invoke `/skills` in Claude Code).

---

## Repository structure

```
.
├── cam/                    ESP32-CAM firmware (C++ / PlatformIO)
│   ├── platformio.ini
│   └── src/
│       ├── main.cpp
│       ├── types/Protocol.h
│       └── communication/
│           ├── CamComm.h
│           └── CamComm.cpp
│
├── robot/                  Robot ESP32 firmware (C++ / PlatformIO)
│   ├── platformio.ini
│   └── src/
│       ├── main.cpp
│       ├── types/
│       │   ├── Protocol.h
│       │   └── MotorTypes.h
│       ├── control/
│       │   ├── WheelController.h
│       │   └── WheelController.cpp
│       └── communication/
│           ├── RobotComm.h
│           └── RobotComm.cpp
│
├── computer/               Python host application (≥ 3.11)
│   ├── main.py             Unified entry point  (--phase 1|2|3)
│   ├── types/              Shared data types and observer interfaces
│   ├── communication/      Transport layer + binary protocol + cam/robot drivers
│   ├── vision/             Vision pipeline stubs (pending implementation)
│   └── manual/             Keyboard controller for Phase 1/2
│
├── emulator/               Robot emulator — TCP loopback, no hardware needed
│   ├── SPEC.md             Emulator design specification
│   └── src/
│       ├── main.py         Entry point
│       ├── robot_emulator.py
│       ├── simulated_robot.py
│       ├── tcp_link.py
│       └── protocol.py
│
├── scripts/
│   └── run.sh              Activates .venv and launches computer/main.py --phase N
│
├── .claude/skills/         Claude Code project skills (invoke with /skill-name)
│   ├── skills/             Index — run /skills to list all available skills
│   ├── sync-message-type/  Add a wire message type across Python + C++ + emulator
│   ├── add-message-type/   Add a wire message on a single link
│   ├── debug-computer-comm/, debug-robot-comm/, debug-cam-comm/, debug-emulator/
│   ├── implement-transport/, implement-detector/, implement-strategy/
│   ├── add-motion-mode/, extend-emulator/
│   └── debug-upload/, debug-serial/, debug-cam-init/, debug-bluetooth/, configure-firmware/
│
├── SPEC.md                 Full system design specification
├── FIRMWARE.md             Toolchain setup, wiring, and flashing guide for both ESP32 boards
├── RUNNING.md              How to run each component (all phases)
├── THREADS.md              Threading model documentation
└── pyproject.toml
```

---

## Development phases

| Phase | Robot | Camera | Goal |
|-------|-------|--------|------|
| **1** | Emulator (TCP) | None | Validate protocol and control logic without hardware |
| **2** | Physical ESP32 (BT) | None | Validate motion over real Bluetooth |
| **3** | Physical ESP32 (BT) | Physical ESP32-CAM (BT) | Full autonomous operation |

### Quick start — Phase 1

```bash
# Terminal 1 — robot emulator
python emulator/src/main.py

# Terminal 2 — keyboard control
bash scripts/run.sh 1
```

### Quick start — Phase 2 / 3

```bash
# Flash robot firmware
cd robot && pio run --target upload

# Flash CAM firmware (Phase 3 only)
cd cam && pio run --target upload

# Run computer
bash scripts/run.sh 2   # or 3
```

---

## System topology

```
┌─────────────────────────────────────────────────────────────────┐
│  ESP32-CAM  (cam/)                                              │
│  IMAGE_CHUNK ──────────────────────────────────────────────►    │
│             ◄─────────────────────────── ACK + HEARTBEAT        │
└─────────────────────────────────────────────────────────────────┘
                        Link A  (BT SPP / Serial)
┌─────────────────────────────────────────────────────────────────┐
│  Computer  (computer/)                                          │
│                                                                 │
│  CamReceiver ──[Frame]──► VisionProcessor ──[FrameResult]──►   │
│                                              BlobFollowerStrategy│
│                                                      │          │
│  RobotSender ◄──────────────────[ControlSignal]──────┘          │
│                                                                 │
│  KeyboardController ──────────[ControlSignal]──► RobotSender   │
└─────────────────────────────────────────────────────────────────┘
                        Link B  (BT SPP / Serial / TCP)
┌─────────────────────────────────────────────────────────────────┐
│  Robot ESP32  (robot/)  OR  Emulator  (emulator/)               │
│             ◄──────────────────────────── CONTROL_REF           │
│  ACK + HEARTBEAT ──────────────────────────────────────────►    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Wire protocol (quick reference)

Both links use identical framing:

```
[0xCA][0xFE]  start
[TYPE]        1 byte
[SEQ]         2 bytes LE uint16
[LEN]         4 bytes LE uint32
[PAYLOAD]     variable
[CRC16]       2 bytes LE  (CRC-16/CCITT over TYPE+SEQ+LEN+PAYLOAD)
[0xED][0xED]  end
```

| Link | Direction | Message | Payload |
|------|-----------|---------|---------|
| A (CAM) | CAM → Computer | `IMAGE_CHUNK` | frame_id, chunk_idx, total_chunks, total_size, jpeg bytes |
| A (CAM) | Computer → CAM | `ACK` | acked_seq, status |
| A (CAM) | Both | `HEARTBEAT` | empty |
| B (Robot) | Computer → Robot | `CONTROL_REF` | angle_deg (float32), speed_ref (float32) |
| B (Robot) | Robot → Computer | `ACK` | acked_seq, status |
| B (Robot) | Both | `HEARTBEAT` | empty |

Full specification: [SPEC.md](SPEC.md).
