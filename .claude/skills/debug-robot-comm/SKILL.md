# Skill: Debug robot firmware communication

## Objective
Diagnose connection, protocol, or control issues on the Robot ESP32 —
WiFi connection issues, missing CONTROL_REF frames, watchdog triggering
emergency stop, or incorrect wheel behaviour.

## Key files
| File | Role |
|------|------|
| `robot/src/communication/RobotComm.h` | Task declarations, RX state machine types |
| `robot/src/communication/RobotComm.cpp` | `_udpTask`, `_controlTask`, `_watchdogTask`, `_dispatchFrame` |
| `robot/src/control/WheelController.cpp` | `_computeTargets`, slew limiter, `emergencyStop` |
| `robot/src/types/Protocol.h` | `MsgType` enum, payload structs, CRC, frame constants |
| `robot/src/main.cpp` | Pin assignments, UDP port |

## Step-by-step

### 1. Open the serial monitor
```bash
cd robot
pio device monitor --baud 115200
```
On boot, the firmware prints:
```
=== Robot ESP32 booting ===
=== Ready ===
```
If you see only garbage, the baud rate is wrong or the port is mismatched.

### 2. Confirm WiFi/UDP connection
After `begin()`, the serial monitor shows:
```
[ROBOT] WiFi IP: 192.168.1.42
[ROBOT] UDP listening on port 5005
```
If WiFi never connects (dots indefinitely), check `robot/src/credentials.h`
SSID/PASS (the file is gitignored; copy from `credentials.example.h` and reflash).

Confirm `PHASE_CONFIGS[2]` (or `[3]`) in `computer/main.py` has the correct IP:
```python
robot_port = "192.168.1.42:5005",
robot_transport = "udp",
```

On the computer side check that `RobotSender.start()` logs `[ROBOT] Sender started`
and that no `Connect failed` retries appear.

### 3. Diagnose first-packet failure / immediate emergency stop
UDP is connectionless — the robot learns the computer's address from the first
received datagram. `_client_port == 0` until the first packet arrives, so
`_sendAck` and `_sendHeartbeat` are silently dropped before that.

The watchdog fires `emergencyStop()` after `WATCHDOG_TIMEOUT_MS = 5000 ms`
with no valid CONTROL_REF or HEARTBEAT. If the robot stops within 5 s and the
computer is sending, the frame is likely failing CRC or the UDP packet is not
arriving.

To confirm: add this log line at the top of `_feedByte`:
```cpp
Serial.printf("[RX] state=%d byte=%02x\n", (int)_rx.state, b);
```
You should see the state machine progress through `WAIT_START_1 → WAIT_START_2
→ READ_HEADER → … → WAIT_END_2` without stalling in `WAIT_START_2`.

### 4. Diagnose watchdog emergency stops
The watchdog fires `WheelController::emergencyStop()` after `WATCHDOG_TIMEOUT_MS = 5000 ms`
(`RobotComm.h:25`) without a valid CONTROL_REF.

Causes:
- Computer is not sending CONTROL_REF (keyboard not pressed in Phase 1/2, or
  vision pipeline not running in Phase 3).
- CRC errors on every received frame — the watchdog only resets on `crc_ok`.
- UDP packet loss or network congestion.
- First-connect resync failure (see §3 above).

Check: add `Serial.println("[WATCH] reset");` inside `_watchdogTask` when
`_last_rx_ms` is updated, and `Serial.println("[WATCH] emergency stop");`
when the timeout fires.

### 5. Diagnose CRC errors
The firmware CRC implementation in `Protocol.h:63-70` must match the Python
`crc16()` in `computer/communication/protocol.py:50-60` exactly.

Quick test: on the computer side, build a CONTROL_REF frame and print its hex:
```python
from computer.communication.protocol import FrameEncoder, ControlRefPayload
enc = FrameEncoder()
frame = enc.build_control_ref(0, ControlRefPayload(0.0, 1.0))
print(frame.hex())
```
Decode the same bytes manually against the C++ CRC formula.

### 6. Diagnose wrong wheel behaviour
If the robot moves in the wrong direction or at the wrong speed:
- Check `LEFT_WHEEL` / `RIGHT_WHEEL` pin assignments in `robot/src/main.cpp:11-14`.
  Swap `pwm` or `dir` pins if a wheel is reversed.
- Check the target formula in `WheelController.cpp:_computeTargets`.
  Expected: `fwd = speed_ref * cosf(rad)`, `turn = speed_ref * sinf(rad)`,
  `left = fwd - turn`, `right = fwd + turn`.
- The slew rate limiter (`MAX_DELTA_PER_TICK = 0.02f` at 50 Hz) means full
  speed takes ~1 s from rest. This is intentional, not a bug.

### 7. Diagnose `emergencyStop` not zeroing wheels immediately
`emergencyStop()` bypasses the slew limiter and directly zeros both `_ref`
targets. If wheels do not stop instantly, the PWM output or H-bridge direction
pin is not zeroed. Check `WheelController.cpp:_applyPwm` (the method that
writes to `ledcWrite` / `digitalWrite`).

## Invariants
- `MAX_PAYLOAD = 16` in `RobotComm.h`. If you add a payload larger than
  16 bytes, increase this constant or the firmware will silently drop frames.
- The watchdog task (`_watchdogTask`) resets `_last_rx_ms` only when a frame
  passes CRC. Frames with bad CRC do NOT reset the watchdog.
- `_tx_mutex` (SemaphoreHandle_t) guards all UDP sends (`_udpSend`). Never
  call `_udp.beginPacket`/`write`/`endPacket` outside `_udpSend`.

## Verification
```bash
# Phase 1: press arrow keys and watch emulator output + serial monitor
python emulator/src/main.py --verbose &
python -m computer.main --phase 1
# Serial monitor should show no watchdog emergency stops
# Emulator should show angle/speed_ref changing on each keypress
```
