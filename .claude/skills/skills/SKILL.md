# Skills Index

Quick reference for all project skills. Invoke any skill with `/skill-name` in Claude Code.

## Protocol

| Skill | When to use |
|-------|-------------|
| `/sync-message-type` | Add a new wire message type across Python, C++ firmware, and emulator simultaneously |
| `/add-message-type` | Add a new wire message on a single link (computer side only) |

## Computer — communication

| Skill | When to use |
|-------|-------------|
| `/debug-computer-comm` | Frames not arriving, CRC errors, heartbeat timeouts, queue issues |
| `/implement-transport` | Add a new link type (WebSocket, UDP, Unix socket, …) |

## Computer — vision

| Skill | When to use |
|-------|-------------|
| `/implement-detector` | Write a new `Detector` subclass (colour, shape, ML model, …) |
| `/implement-strategy` | Write a new `ControlStrategy` that converts detections to motor commands |

## Robot firmware

| Skill | When to use |
|-------|-------------|
| `/debug-robot-comm` | BT pairing failures, watchdog triggers, wrong wheel behaviour |
| `/add-motion-mode` | Add spin-in-place, forward-only, or any new drive mode |

## CAM firmware

| Skill | When to use |
|-------|-------------|
| `/debug-cam-comm` | Camera init failure, frames not streaming, heartbeat timeout |

## Emulator

| Skill | When to use |
|-------|-------------|
| `/debug-emulator` | TCP connection issues, threads dying, wrong wheel output, CRC errors |
| `/extend-emulator` | Add battery simulation, encoder feedback, or new mock messages |

## Firmware (hardware setup and debugging)

| Skill | When to use |
|-------|-------------|
| `/debug-upload` | `Failed to connect to ESP32`, bootloader mode, FTDI wiring, upload speed |
| `/debug-serial` | Garbage output in serial monitor, `Permission denied`, wrong baud rate |
| `/debug-cam-init` | `camera init failed`, ribbon cable, frame streaming and quality issues |
| `/debug-bluetooth` | BT device not found, serial port missing, `rfcomm bind`, wrong BT name |
| `/configure-firmware` | Change motor pins, BT names, frame rate, JPEG quality, rate limiter |
