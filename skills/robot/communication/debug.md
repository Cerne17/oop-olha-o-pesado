# Skill: Debug robot firmware communication

## Objective
Diagnose connection, protocol, or control issues on the Robot ESP32 —
Bluetooth pairing failures, missing CONTROL_REF frames, watchdog triggering
emergency stop, or incorrect wheel behaviour.

## Key files
| File | Role |
|------|------|
| `robot/src/communication/RobotComm.h` | Task declarations, RX state machine types |
| `robot/src/communication/RobotComm.cpp` | `_btTask`, `_controlTask`, `_watchdogTask`, `_dispatchFrame` |
| `robot/src/control/WheelController.cpp` | `_computeTargets`, slew limiter, `emergencyStop` |
| `robot/src/types/Protocol.h` | `MsgType` enum, payload structs, CRC, frame constants |
| `robot/src/main.cpp` | Pin assignments, BT name |

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

### 2. Confirm Bluetooth connection
After `begin()` the `_btTask` polls `_bt.available()`. The computer connects
via `SerialTransport` or `RFCOMMTransport`. Add a temporary `Serial.println`
in `RobotComm.cpp:_btTask` to log when `_bt.available() > 0` for the first time.

On the computer side check that `RobotSender.start()` logs `[ROBOT] Sender started`
and that no `Connect failed` retries appear.

### 3. Diagnose watchdog emergency stops
The watchdog fires `WheelController::emergencyStop()` after `WATCHDOG_TIMEOUT_MS = 3000 ms`
(`RobotComm.h:25`) without a valid CONTROL_REF.

Causes:
- Computer is not sending CONTROL_REF (keyboard not pressed in Phase 1/2, or
  vision pipeline not running in Phase 3).
- CRC errors on every received frame — the watchdog only resets on `crc_ok`.
- BT link has too much latency.

Check: add `Serial.println("[WATCH] reset");` inside `_watchdogTask` when
`_last_rx_ms` is updated, and `Serial.println("[WATCH] emergency stop");`
when the timeout fires.

### 4. Diagnose CRC errors
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

### 5. Diagnose wrong wheel behaviour
If the robot moves in the wrong direction or at the wrong speed:
- Check `LEFT_WHEEL` / `RIGHT_WHEEL` pin assignments in `robot/src/main.cpp:11-14`.
  Swap `pwm` or `dir` pins if a wheel is reversed.
- Check the target formula in `WheelController.cpp:_computeTargets`.
  Expected: `fwd = speed_ref * cosf(rad)`, `turn = speed_ref * sinf(rad)`,
  `left = fwd - turn`, `right = fwd + turn`.
- The slew rate limiter (`MAX_DELTA_PER_TICK = 0.02f` at 50 Hz) means full
  speed takes ~1 s from rest. This is intentional, not a bug.

### 6. Diagnose `emergencyStop` not zeroing wheels immediately
`emergencyStop()` bypasses the slew limiter and directly zeros both `_ref`
targets. If wheels do not stop instantly, the PWM output or H-bridge direction
pin is not zeroed. Check `WheelController.cpp:_applyPwm` (the method that
writes to `ledcWrite` / `digitalWrite`).

## Invariants
- `MAX_PAYLOAD = 16` in `RobotComm.h:77`. If you add a payload larger than
  16 bytes, increase this constant or the firmware will silently drop frames.
- The watchdog task (`_watchdogTask`) resets `_last_rx_ms` only when a frame
  passes CRC. Frames with bad CRC do NOT reset the watchdog.
- `_tx_mutex` (SemaphoreHandle_t) guards all BT writes. Never call `_bt.write`
  outside `_btTask` without taking this mutex.

## Verification
```bash
# Phase 1: press arrow keys and watch emulator output + serial monitor
python emulator/src/main.py --verbose &
python -m computer.main --phase 1
# Serial monitor should show no watchdog emergency stops
# Emulator should show angle/speed_ref changing on each keypress
```
