# Skills Index

Self-contained instruction sets for agentic development on this codebase.
Each skill is a markdown file that tells an agent exactly which files to read,
what steps to follow, what invariants to preserve, and how to verify the work.

## How to use a skill
Point an agent at the relevant skill file as part of your prompt:
> "Follow the steps in `skills/computer/communication/implement_transport.md`
> to add a WebSocket transport."

---

## Computer — communication

| Skill | When to use |
|-------|-------------|
| [debug.md](computer/communication/debug.md) | Frames not arriving, CRC errors, heartbeat timeouts, queue issues |
| [implement_transport.md](computer/communication/implement_transport.md) | Add a new link type (WebSocket, UDP, Unix socket, …) |
| [add_message_type.md](computer/communication/add_message_type.md) | Add a new wire message to Link A or Link B from the computer side |

## Computer — vision

| Skill | When to use |
|-------|-------------|
| [implement_detector.md](computer/vision/implement_detector.md) | Write a new `Detector` subclass (colour, shape, ML model, …) |
| [implement_strategy.md](computer/vision/implement_strategy.md) | Write a new `ControlStrategy` that converts detections to motor commands |

## Robot firmware

| Skill | When to use |
|-------|-------------|
| [communication/debug.md](robot/communication/debug.md) | BT pairing failures, watchdog triggers, wrong wheel behaviour |
| [control/add_motion_mode.md](robot/control/add_motion_mode.md) | Add spin-in-place, forward-only, or any new drive mode |

## CAM firmware

| Skill | When to use |
|-------|-------------|
| [communication/debug.md](cam/communication/debug.md) | Camera init failure, frames not streaming, heartbeat timeout |

## Emulator

| Skill | When to use |
|-------|-------------|
| [debug.md](emulator/debug.md) | TCP connection issues, threads dying, wrong wheel output, CRC errors |
| [extend_mock.md](emulator/extend_mock.md) | Add battery simulation, encoder feedback, or new mock messages |

## Protocol (cross-cutting)

| Skill | When to use |
|-------|-------------|
| [sync_message_type.md](protocol/sync_message_type.md) | Add a new message type that touches Python, C++ firmware, AND emulator simultaneously |

## Firmware (hardware setup and debugging)

| Skill | When to use |
|-------|-------------|
| [firmware/debug_upload.md](firmware/debug_upload.md) | `Failed to connect to ESP32`, bootloader mode, FTDI wiring, upload speed |
| [firmware/debug_serial.md](firmware/debug_serial.md) | Garbage output in serial monitor, `Permission denied`, wrong baud rate |
| [firmware/debug_cam_init.md](firmware/debug_cam_init.md) | `camera init failed`, ribbon cable, frame streaming and quality issues |
| [firmware/debug_bluetooth.md](firmware/debug_bluetooth.md) | BT device not found, serial port missing, `rfcomm bind`, wrong BT name |
| [firmware/configure_hardware.md](firmware/configure_hardware.md) | Change motor pins, BT names, frame rate, JPEG quality, rate limiter |
