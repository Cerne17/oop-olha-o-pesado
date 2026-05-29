# Graph Report - .  (2026-05-23)

## Corpus Check
- Corpus is ~40,964 words - fits in a single context window. You may not need a graph.

## Summary
- 525 nodes · 814 edges · 40 communities (29 shown, 11 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 79 edges (avg confidence: 0.6)
- Token cost: 37,000 input · 7,400 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Image Assembly Pipeline|Image Assembly Pipeline]]
- [[_COMMUNITY_Transport Layer Abstractions|Transport Layer Abstractions]]
- [[_COMMUNITY_Emulator Core|Emulator Core]]
- [[_COMMUNITY_Phase Routing & TCP|Phase Routing & TCP]]
- [[_COMMUNITY_Vision Processing|Vision Processing]]
- [[_COMMUNITY_Wire Protocol Codec|Wire Protocol Codec]]
- [[_COMMUNITY_Motor Control|Motor Control]]
- [[_COMMUNITY_CAM Firmware|CAM Firmware]]
- [[_COMMUNITY_Bug Diagnosis & Fixes|Bug Diagnosis & Fixes]]
- [[_COMMUNITY_Project Skills Index|Project Skills Index]]
- [[_COMMUNITY_Robot Communication|Robot Communication]]
- [[_COMMUNITY_Hardware Wiring & Firmware|Hardware Wiring & Firmware]]
- [[_COMMUNITY_Camera Receiver|Camera Receiver]]
- [[_COMMUNITY_Claude Config & Plugins|Claude Config & Plugins]]
- [[_COMMUNITY_Dependencies & Blob Detection|Dependencies & Blob Detection]]
- [[_COMMUNITY_Project Overview & Spec|Project Overview & Spec]]
- [[_COMMUNITY_Message Type Management|Message Type Management]]
- [[_COMMUNITY_Type System & Observers|Type System & Observers]]
- [[_COMMUNITY_Heartbeat & Watchdog|Heartbeat & Watchdog]]
- [[_COMMUNITY_Keyboard Control & TX|Keyboard Control & TX]]
- [[_COMMUNITY_Control Reference & Drive|Control Reference & Drive]]
- [[_COMMUNITY_Firmware Configuration|Firmware Configuration]]
- [[_COMMUNITY_Image Generator|Image Generator]]
- [[_COMMUNITY_Manual Keyboard Control|Manual Keyboard Control]]
- [[_COMMUNITY_Emulator Docs & Transport|Emulator Docs & Transport]]
- [[_COMMUNITY_CRC & Debug Skills|CRC & Debug Skills]]
- [[_COMMUNITY_Transport Interface|Transport Interface]]
- [[_COMMUNITY_Vision Strategy Pattern|Vision Strategy Pattern]]
- [[_COMMUNITY_Control Signals & Buzzer|Control Signals & Buzzer]]
- [[_COMMUNITY_Run Scripts|Run Scripts]]
- [[_COMMUNITY_State Signals|State Signals]]
- [[_COMMUNITY_Local Settings|Local Settings]]
- [[_COMMUNITY_C++ Code Standards|C++ Code Standards]]
- [[_COMMUNITY_Communication Init|Communication Init]]
- [[_COMMUNITY_Computer Package Init|Computer Package Init]]
- [[_COMMUNITY_Manual Package Init|Manual Package Init]]
- [[_COMMUNITY_Vision Package Init|Vision Package Init]]
- [[_COMMUNITY_Transport Rationale|Transport Rationale]]
- [[_COMMUNITY_TODO List|TODO List]]
- [[_COMMUNITY_Closed-Loop PID|Closed-Loop PID]]

## God Nodes (most connected - your core abstractions)
1. `RobotSender` - 22 edges
2. `CamReceiver` - 19 edges
3. `EmulatorApp` - 18 edges
4. `Frame` - 16 edges
5. `KeyboardController` - 16 edges
6. `ControlSignal` - 15 edges
7. `RobotEmulator` - 15 edges
8. `ComputerVision` - 14 edges
9. `SerialTransport` - 13 edges
10. `FrameEncoder` - 13 edges

## Surprising Connections (you probably didn't know these)
- `Newest-Wins Queue Pattern (maxsize=1 overflow eviction)` --semantically_similar_to--> `Heartbeat / Watchdog Pattern (1 Hz HB, 5s timeout)`  [INFERRED] [semantically similar]
  THREADS.md → SPEC.md
- `CONTROL_REF Payload (angle_deg + speed_ref)` --semantically_similar_to--> `ControlSignal`  [INFERRED] [semantically similar]
  emulator/SPEC.md → .claude/skills/implement-strategy/SKILL.md
- `RobotEmulator` --uses--> `FrameEncoder`  [INFERRED]
  emulator/src/robot_emulator.py → computer/communication/protocol.py
- `EmulatorApp` --uses--> `FrameEncoder`  [INFERRED]
  emulator/src/emulator.py → computer/communication/protocol.py
- `RobotEmulator` --uses--> `FrameDecoder`  [INFERRED]
  emulator/src/robot_emulator.py → computer/communication/protocol.py

## Hyperedges (group relationships)
- **Phase 3 Vision Pipeline Data Flow (CAM → Computer → Robot)** — spec_cam_receiver, spec_vision_processor, spec_blob_follower_strategy, spec_robot_sender [EXTRACTED 1.00]
- **Observer Pattern Chain (FrameObservable → ResultObservable → ControlObservable)** — spec_observer_pattern, spec_cam_receiver, spec_vision_processor, spec_blob_follower_strategy, spec_robot_sender [EXTRACTED 1.00]
- **BT Buffer Overflow → State Machine Resync Bug Chain** — diagnosis_bug2_bt_fifo, diagnosis_bug1_wait_start2, diagnosis_state_machine_resync [EXTRACTED 1.00]
- **Message Type Synchronisation Across Python, C++ Firmware, and Emulator** — sync_message_type_skill, add_message_type_skill, little_endian_struct_invariant [EXTRACTED 1.00]
- **Control Signal Pipeline: Strategy → ControlSignal → RobotSender** — blob_follower_strategy, control_signal, control_ref_payload [INFERRED 0.85]
- **Emulator Core: TCP Server + RX Loop + SimulatedRobot** — emulator_tcp_server, emulator_rx_loop, simulated_robot [EXTRACTED 1.00]

## Communities (40 total, 11 thin omitted)

### Community 0 - "Image Assembly Pipeline"
Cohesion: 0.06
Nodes (27): _FrameBuffer, ImageAssembler, computer.communication.assembler — reassembles IMAGE_CHUNK messages into Frames., Process one received IMAGE_CHUNK payload.          Returns a complete Frame when, CamReceiver, computer.communication.cam_receiver — manages Link A (Computer ↔ CAM).  Receives, Parameters     ----------     transport : Transport — constructed but not yet co, AckPayload (+19 more)

### Community 1 - "Transport Layer Abstractions"
Cohesion: 0.05
Nodes (21): computer.communication.transport — concrete Transport implementations.  SerialTr, TCP client transport. Connects to a server at (host, port).      Works for any T, UDP datagram transport. Each send() call is one datagram to (host, port).     re, pyserial-backed transport. Works on macOS (paired BT SPP device shows up     as, Linux-only AF_BLUETOOTH RFCOMM socket transport. Does not require the     device, RFCOMMTransport, SerialTransport, TCPTransport (+13 more)

### Community 2 - "Emulator Core"
Cohesion: 0.06
Nodes (11): EmulatorApp, emulator.emulator — EmulatorApp, the main thread orchestrator., KeyboardInput, emulator.keyboard_input — non-blocking arrow key state via pynput., Returns (angle_deg, stop).         angle_deg: clockwise from straight forward., emulator.serial_link — serial port wrapper with thread-safe TX., SerialLink, _compute_targets() (+3 more)

### Community 3 - "Phase Routing & TCP"
Cohesion: 0.07
Nodes (14): main(), emulator.main -- CLI entry point for the robot emulator.  Run from the emulator, emulator.robot_emulator -- RobotEmulator orchestrator.  Accepts one TCP connecti, Signal all loops to exit and close the server socket., Open the server socket, then loop: accept -> spawn threads -> wait for         d, RobotEmulator, emulator.tcp_link -- TCP server socket wrapper with thread-safe TX.  The emulato, Create and bind the server socket. Call once at startup. (+6 more)

### Community 4 - "Vision Processing"
Cohesion: 0.11
Nodes (20): ComputerVision, hand_landmarker_options(), Coordena execução do programa na thread principal., Método obrigatório do FrameObserver.         Chamado automaticamente pelo CamRec, detect_persons(), get_matching_person(), identify_gesture(), init_person_detector() (+12 more)

### Community 5 - "Wire Protocol Codec"
Cohesion: 0.12
Nodes (11): crc16(), DecodedFrame, FrameDecoder, FrameEncoder, emulator.protocol -- binary protocol for Link B (Computer <-> Robot).  Self-cont, Returns (acked_seq, status)., Feed raw bytes; yields DecodedFrame objects as they become complete., CRC-16/CCITT XModem: poly=0x1021, init=0x0000, no reflection. (+3 more)

### Community 6 - "Motor Control"
Cohesion: 0.13
Nodes (5): _clamp(), _computeTargets(), _driveMotor(), _slew(), update()

### Community 7 - "CAM Firmware"
Cohesion: 0.15
Nodes (10): begin(), _cameraTask(), _dispatchFrame(), _feedByte(), _initCamera(), _resetRx(), _rxTask(), _sendChunk() (+2 more)

### Community 8 - "Bug Diagnosis & Fixes"
Cohesion: 0.21
Nodes (13): Transport Abstraction (Serial/RFCOMM/TCP/UDP all implement Transport ABC), Bug 1: WAIT_START_2 Drops START_1 Byte (CRITICAL), Bug 2: BluetoothSerial RX FIFO Too Small (512B overflow), Bug 3: WAIT_END_1 Drops START_1 Byte (DESYNC), Bug 4: memcpy(nullptr, 0) in _buildFrame (UB), Bug 5: READ_PAYLOAD Missing Upper-Bound Check (LATENT), Bug 6: READ_HEADER Struct Overlay (FRAGILE), BT SPP Handshake Buffer Overflow Diagnosis (+5 more)

### Community 9 - "Project Skills Index"
Cohesion: 0.22
Nodes (13): CLAUDE.md Project Instructions, Custom Claude Code Skills (.claude/skills/), Skill: debug-emulator (Phase 1 TCP emulator debugging), Skill: debug-robot-comm (robot firmware communication debugging), Skill: extend-emulator (add mock behaviour to emulator), CamComm (FreeRTOS camera + RX tasks, UDP streaming), CRC-16/CCITT XModem Algorithm, FreeRTOS Task Architecture (btTask/controlTask/watchdogTask/cameraTask) (+5 more)

### Community 10 - "Robot Communication"
Cohesion: 0.28
Nodes (8): _buildFrame(), _dispatchFrame(), _feedByte(), _resetRx(), _sendAck(), _sendHeartbeat(), _udpSend(), _udpTask()

### Community 11 - "Hardware Wiring & Firmware"
Cohesion: 0.17
Nodes (13): PlatformIO Build System (ESP32 firmware), ESP32-CAM AI Thinker Wiring and Flashing, GPIO0 Bootloader Mode Procedure (ESP32-CAM), Firmware Setup Guide (FIRMWARE.md), OV2640 Camera Pin Map (AI Thinker hardcoded), Robot ESP32 Hardware Wiring (L298N H-Bridge), Running Guide (RUNNING.md), MediaPipe Hand Landmarker Model (hand_landmarker.task) (+5 more)

### Community 12 - "Camera Receiver"
Cohesion: 0.22
Nodes (5): FrameObservable, on_frame(), Mixin for classes that produce Frame events., Frame, ImageReceiver

### Community 13 - "Claude Config & Plugins"
Cohesion: 0.22
Nodes (10): source, enabledPlugins, ecc@ecc, fullstack-dev-skills@fullstack-dev-skills, extraKnownMarketplaces, ecc, fullstack-dev-skills, source (+2 more)

### Community 14 - "Dependencies & Blob Detection"
Cohesion: 0.25
Nodes (11): numpy >=1.24, opencv-python >=4.8, pyserial >=3.5, Python Dependencies (requirements.txt), Skill: implement-detector (vision detector implementation guide), BlobFollowerStrategy (ResultObserver + ControlObservable), ColourBlobDetector (HSV range contour detector), Detection Dataclass (label, confidence, bbox) (+3 more)

### Community 15 - "Project Overview & Spec"
Cohesion: 0.22
Nodes (11): Autonomous Cargo-Carrying Robot (end-to-end system), README: Robot Vision System Project Overview, System Topology (ESP32-CAM + Computer + Robot ESP32), Wire Protocol Quick Reference, AckPayload (acked_seq, status), ImageChunkHeader (frame_id, chunk_idx, total_chunks, total_size), Link A Message Types (IMAGE_CHUNK, ACK, HEARTBEAT), Link B Message Types (CONTROL_REF, ACK, HEARTBEAT) (+3 more)

### Community 16 - "Message Type Management"
Cohesion: 0.27
Nodes (11): Add Message Type Skill, Add Motion Mode Skill, Baud Rate 115200 Invariant, Cross-Layer Message Type Synchronisation, Debug Serial Skill, Debug Upload Skill, ESP32-CAM Manual Bootloader Procedure, Little-Endian Struct Invariant (ESP32 Xtensa) (+3 more)

### Community 17 - "Type System & Observers"
Cohesion: 0.36
Nodes (7): ABC, computer.types — shared interfaces and pure data types.  No I/O, no threading, n, ControlObserver, FrameObserver, computer.types.observers — Observer pattern ABCs and Observable mixins.  Observe, ControlSignal, DummyRobot

### Community 18 - "Heartbeat & Watchdog"
Cohesion: 0.31
Nodes (10): Heartbeat / Watchdog Pattern (1 Hz HB, 5s timeout), UDP Bootstrap via Proactive Heartbeat (CAM learns computer IP:port), Bluetooth Classic SPP Pairing (RobotESP32 device name), Phase 2 Manual Control Bluetooth Guide (PHASE2_GUIDE.md), Watchdog 5s Safety Cutoff (no CONTROL_REF or HEARTBEAT), Skill: debug-cam-comm (CAM firmware communication debugging), CamReceiver (Link A orchestrator, FrameObservable), Frame Dataclass (frame_id, jpeg bytes, timestamp) (+2 more)

### Community 19 - "Keyboard Control & TX"
Cohesion: 0.29
Nodes (10): pynput >=1.7, KeyboardController (arrow-key ControlObservable, 20 Hz), RobotSender (Link B TX, ControlObserver), Daemon Thread Pattern (auto-kill on main exit), keyboard-pub Thread (KeyboardController._publish_loop), Threading Model Documentation, Newest-Wins Queue Pattern (maxsize=1 overflow eviction), pynput OS Key Listener Thread (+2 more)

### Community 20 - "Control Reference & Drive"
Cohesion: 0.24
Nodes (10): CONTROL_REF Payload (angle_deg + speed_ref), DriveMode Enum, Emulator RX Loop, Emulator Self-Contained Protocol Copy Rationale, Robot Emulator Implementation Specification v2, Emulator TCP Server (localhost:5001), Emulator Threading Model, FrameDecoder State Machine (+2 more)

### Community 21 - "Firmware Configuration"
Cohesion: 0.22
Nodes (10): CAM UDP Port Configuration, Configure Firmware Skill, JPEG Quality and Resolution Config, WheelController Rate Limiter Config, Robot UDP Port Configuration, ESP32-CAM Target FPS Configuration, Use UDP Transport Skill, WheelController Slew Rate Limiter (+2 more)

### Community 23 - "Manual Keyboard Control"
Cohesion: 0.22
Nodes (4): computer.manual.keyboard — KeyboardController.  Reads arrow key state via pynput, ControlObservable, on_control(), Mixin for classes that produce ControlSignal events.

### Community 24 - "Emulator Docs & Transport"
Cohesion: 0.25
Nodes (8): Emulator README, Emulator requirements.txt, Image Mode: Blob (moving red circle), Implement Transport Skill, receive_available Non-Blocking Invariant, socat Virtual Serial Port Pair (legacy Phase 1), TCPTransport, Transport ABC (Abstract Base Class)

### Community 25 - "CRC & Debug Skills"
Cohesion: 0.33
Nodes (7): CRC-16/CCITT XModem Algorithm, Debug Computer Communication Skill, Debug UDP Skill, ImageAssembler (multi-chunk JPEG reassembly), Newest-Wins Queue Pattern, UDP Address Learning (ESP32 client discovery), UDP Watchdog Timer Pattern

### Community 27 - "Vision Strategy Pattern"
Cohesion: 0.53
Nodes (6): BlobFollowerStrategy, ControlObservable ABC, ControlSignal, FrameResult, Implement Strategy Skill, ResultObserver ABC

### Community 28 - "Control Signals & Buzzer"
Cohesion: 0.60
Nodes (5): Robot Indicator Outputs (Yellow/Green/Red LED + Buzzer GPIO), ControlRefPayload (angle_deg, speed_ref, buzzer, leds), ControlSignal Dataclass (angle_deg, speed_ref, buzzer, leds), ControlSignal Factory Methods (waiting, following, lost), TODO: Buzzer and LED Signals to Robot (JVP)

### Community 29 - "Run Scripts"
Cohesion: 0.70
Nodes (4): error(), info(), warn(), run.sh script

### Community 32 - "C++ Code Standards"
Cohesion: 0.67
Nodes (3): C++ Firmware Naming Convention, Hardware Truth Table Documentation Pattern, Sanitize C++ Firmware Skill

## Knowledge Gaps
- **30 isolated node(s):** `fullstack-dev-skills@fullstack-dev-skills`, `ecc@ecc`, `allow`, `pyserial >=3.5`, `pynput OS Key Listener Thread` (+25 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `FrameEncoder` connect `Image Assembly Pipeline` to `Emulator Core`, `Phase Routing & TCP`?**
  _High betweenness centrality (0.160) - this node is a cross-community bridge._
- **Why does `EmulatorApp` connect `Emulator Core` to `Image Assembly Pipeline`, `Image Generator`?**
  _High betweenness centrality (0.139) - this node is a cross-community bridge._
- **Why does `RobotEmulator` connect `Phase Routing & TCP` to `Image Assembly Pipeline`, `Emulator Core`?**
  _High betweenness centrality (0.120) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `RobotSender` (e.g. with `ControlObserver` and `PhaseConfig`) actually correct?**
  _`RobotSender` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `CamReceiver` (e.g. with `FrameObservable` and `PhaseConfig`) actually correct?**
  _`CamReceiver` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `EmulatorApp` (e.g. with `FrameDecoder` and `FrameEncoder`) actually correct?**
  _`EmulatorApp` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `Frame` (e.g. with `FrameObserver` and `ControlObserver`) actually correct?**
  _`Frame` has 8 INFERRED edges - model-reasoned connections that need verification._