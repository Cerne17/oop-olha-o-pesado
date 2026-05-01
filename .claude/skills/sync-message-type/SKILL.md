# Skill: Synchronise a new message type across all layers

## Objective
Add a new wire message type end-to-end: Python computer, C++ firmware, and
Python emulator — ensuring numeric values, payload layouts, and dispatch logic
are consistent across all three codebases.

This skill orchestrates the individual per-module skills. Use it when a change
touches more than one layer simultaneously.

## Checklist

A new message type on **Link B (Robot)** touches 4 files.
A new message type on **Link A (CAM)** touches 3 files (no emulator yet).

### Link B (Computer ↔ Robot ↔ Emulator)

- [ ] `computer/communication/protocol.py` — add to `RobotMsg`, add payload dataclass, add encoder method
- [ ] `computer/communication/robot_sender.py` OR `cam_receiver.py` — add dispatch branch
- [ ] `robot/src/types/Protocol.h` — add to `MsgType` enum, add packed struct
- [ ] `robot/src/communication/RobotComm.cpp` — add case in `_dispatchFrame()`
- [ ] `emulator/src/protocol.py` — add constant, add decode helper
- [ ] `emulator/src/robot_emulator.py` — add dispatch branch in `_rx_loop`
- [ ] `robot/src/communication/RobotComm.h` — update `MAX_PAYLOAD` if new payload is larger

### Link A (Computer ↔ CAM)

- [ ] `computer/communication/protocol.py` — add to `CamMsg`, add payload dataclass, add encoder method
- [ ] `computer/communication/cam_receiver.py` — add dispatch branch in `_rx_loop`
- [ ] `cam/src/types/Protocol.h` — add to `MsgType` enum, add packed struct
- [ ] `cam/src/communication/CamComm.cpp` — add case in `_dispatchFrame()`
- [ ] `cam/src/communication/CamComm.h` — update `MAX_PAYLOAD` if needed

## Step-by-step

### 1. Pick a message type value
Check all existing values:

| Link | Value | Name |
|------|-------|------|
| A (CAM) | 0x01 | IMAGE_CHUNK |
| A (CAM) | 0x02 | ACK |
| A (CAM) | 0x03 | HEARTBEAT |
| B (Robot) | 0x01 | CONTROL_REF |
| B (Robot) | 0x02 | ACK |
| B (Robot) | 0x03 | HEARTBEAT |

The two links have **independent** namespaces — the same value can be reused
across links. Pick the next available value within the target link's namespace.

### 2. Define the payload layout on paper first
Specify every field with type and byte order before writing any code.
Example:
```
MyPayload (Link B, 0x04)
  offset 0  uint16 LE  field_a
  offset 2  float32 LE field_b
  total 6 bytes
  struct format: '<Hf'
```
Both Python and C++ must use the same layout.

### 3. Apply changes in order

**Python (computer) first — easiest to iterate:**
Follow `/add-message-type` steps 1–4.

**C++ firmware second:**
Follow `/add-message-type` steps 5–6.
The struct format in C++ must be `__attribute__((packed))`.

Key alignment rule: ESP32 (Xtensa LX6) is little-endian. `memcpy` into a
packed struct is safe. Do not use pointer casts on unaligned data.

**Emulator third (Link B only):**
Follow `/add-message-type` step 7.

### 4. Update `MAX_PAYLOAD` in firmware if needed
`robot/src/communication/RobotComm.h:77`:
```cpp
static constexpr size_t MAX_PAYLOAD = 16;  // must be >= sizeof(largest payload)
```
If your new payload exceeds 16 bytes, increase this constant.

Same for `cam/src/communication/CamComm.h:78`:
```cpp
static constexpr size_t MAX_PAYLOAD = 8;
```

### 5. Cross-check numeric values
After writing all files, grep for the hex value across the codebase:
```bash
grep -r "0x04" computer/communication/protocol.py \
              robot/src/types/Protocol.h \
              emulator/src/protocol.py
```
All three must show the same assignment for the same semantic name.

### 6. Cross-check struct sizes
Python:
```python
from computer.communication.protocol import MyPayload
import struct; print(struct.calcsize(MyPayload._FMT))
```
C++:
```cpp
Serial.printf("sizeof(MyPayload)=%d\n", sizeof(Protocol::MyPayload));
```
Both must print the same number.

## Common mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Value mismatch between Python and C++ | Frames decoded as wrong type | Grep for the hex value in all files |
| Struct format uses `>` (big-endian) | Corrupted field values | Always use `<` in Python; ESP32 is LE |
| `MAX_PAYLOAD` not updated | Firmware silently drops new frames | Increase `MAX_PAYLOAD` to match new size |
| Missing `__attribute__((packed))` in C++ | Struct has padding bytes, size mismatch | Add the attribute |
| Emulator not updated (Link B) | Phase 1 test passes, Phase 2 fails | Always update emulator in the same PR |

## Verification
```bash
# 1. Phase 1 end-to-end
python emulator/src/main.py --verbose &
python -m computer.main --phase 1
# New message type should appear in --verbose output with crc_ok=True

# 2. Firmware serial monitor
cd robot && pio run --target upload
pio device monitor
# New message should be dispatched without unknown-type ACK (status=2)
```
