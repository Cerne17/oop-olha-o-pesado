# Skill: Debug computer communication issues

## Objective
Diagnose and fix failures in `computer/communication/` — connection drops,
missing frames, CRC errors, heartbeat timeouts, or the robot/cam not responding.

## Key files
| File | Role |
|------|------|
| `computer/communication/cam_receiver.py` | Link A RX loop, heartbeat watchdog, ACK sender |
| `computer/communication/robot_sender.py` | Link B TX loop, newest-wins queue, heartbeat sender |
| `computer/communication/transport.py` | `SerialTransport`, `RFCOMMTransport`, `TCPTransport` |
| `computer/communication/protocol.py` | `FrameDecoder`, `FrameEncoder`, payload structs |
| `computer/communication/assembler.py` | `ImageAssembler` — multi-chunk JPEG reassembly |
| `computer/main.py` | `PHASE_CONFIGS` — ports, transport kinds |

## Step-by-step

### 1. Confirm the transport connects
Read `computer/main.py` lines 62–72 (`_make_transport`).
Check `PHASE_CONFIGS` for the active phase — verify the port string is correct.

For Phase 1 confirm the emulator is listening:
```bash
python emulator/src/main.py --port 5001 --verbose
```
For Phase 2/3 confirm the Bluetooth serial device exists:
```bash
ls /dev/cu.Robot*          # macOS
ls /dev/rfcomm*            # Linux
```

### 2. Add temporary verbose logging
`CamReceiver._rx_loop` and `RobotSender._tx_loop` do not have a verbose flag;
add `print` statements around the `for frame in self._decoder.feed(raw):` loop
to dump raw hex and decoded fields.

Minimal probe to paste into `cam_receiver.py:_rx_loop` after the `feed()` call:
```python
print(f"[DBG] frame type={frame.msg_type:#04x} seq={frame.seq_num} crc_ok={frame.crc_ok} payload={frame.payload.hex()}")
```

### 3. Check CRC errors
If `frame.crc_ok` is `False` consistently:
- The byte stream is corrupted — check baud rate (Serial: must be 115200).
- There is a framing mismatch — compare `_START_1/_START_2/_END_1/_END_2`
  constants between `computer/communication/protocol.py:18-21` and the firmware
  `Protocol.h` (`FRAME_START_1=0xCA FRAME_START_2=0xFE FRAME_END_1=0xED FRAME_END_2=0xED`).
- Run `FrameDecoder` in isolation with a known-good captured byte string.

### 4. Check heartbeat timeouts
`CamReceiver` warns after 5 s without a HEARTBEAT from the CAM
(`cam_receiver.py:110`). `RobotSender` sends a HEARTBEAT every 1 s when idle
(`robot_sender.py:138`).

If the CAM heartbeat warning fires:
- CAM firmware sends HEARTBEAT in `_rxTask` on receiving a HEARTBEAT from the computer.
  Check `cam/src/communication/CamComm.cpp:290-294`.
- Confirm the computer is sending heartbeats — add a print in `robot_sender.py:_tx_loop`
  near the `build_heartbeat` call.

### 5. Check the robot sender queue
`RobotSender` uses a `queue.Queue(maxsize=1)` with newest-wins overflow
(`robot_sender.py:39`). If `on_control()` is never called, `_tx_loop` only
sends heartbeats. Verify `KeyboardController._publish_loop` is running and
calling `_notify_control()` → `RobotSender.on_control()`.

Add a counter probe:
```python
# in RobotSender.on_control():
print(f"[DBG] on_control angle={signal.angle_deg:.1f} speed={signal.speed_ref:.2f}")
```

### 6. Check image assembly (Phase 3)
`ImageAssembler.on_chunk()` in `computer/communication/assembler.py` drops
a frame if all chunks do not arrive within `frame_timeout_s=2.0` seconds.
Call `cam_receiver.stats()` and inspect `pending` — if it stays > 0 and
`rx_images` never increases, chunks are arriving but not completing.

Check `IMAGE_CHUNK_DATA_SIZE` (512) matches on both Python and C++ sides:
- Python: `computer/communication/protocol.py:43`
- C++: `cam/src/types/Protocol.h:31`

## Invariants
- Never change `_START_1/_START_2/_END_1/_END_2` without updating all three
  `Protocol.h` files and `emulator/src/protocol.py` simultaneously.
- CRC covers bytes from `MSG_TYPE` through end of `PAYLOAD` — not the start
  or end bytes. See `protocol.py:141`.
- Sequence numbers are per-sender, uint16, roll over at 65535. They are never
  validated for ordering — only used for ACK matching.

## Verification
```bash
# Phase 1 end-to-end with verbose emulator
python emulator/src/main.py --verbose &
python -m computer.main --phase 1
# Press an arrow key — emulator must print CONTROL_REF and RX count must increase
```
