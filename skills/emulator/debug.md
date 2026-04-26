# Skill: Debug the robot emulator

## Objective
Diagnose failures in the Phase 1 robot emulator — TCP connection issues,
frames not arriving, wrong wheel output, or threads not starting.

## Key files
| File | Role |
|------|------|
| `emulator/src/robot_emulator.py` | Main orchestrator, all 4 threads |
| `emulator/src/tcp_link.py` | TCP server socket wrapper |
| `emulator/src/protocol.py` | `FrameDecoder`, `FrameEncoder`, message types |
| `emulator/src/simulated_robot.py` | Wheel model |
| `emulator/src/main.py` | CLI entry point |

## Step-by-step

### 1. Start with `--verbose`
```bash
python emulator/src/main.py --port 5001 --verbose
```
`--verbose` logs every decoded incoming frame and every sent frame.
Expected output after computer connects:
```
[EMU] Computer connected from 127.0.0.1
[HB] HEARTBEAT sent
[RX] CONTROL_REF angle=0.0 speed=+1.00
[RX] HEARTBEAT
```

### 2. "Address already in use" on startup
The TCP server socket from a previous run was not closed cleanly.
`tcp_link.py:33` sets `SO_REUSEADDR`, which normally prevents this.
If the error still occurs:
```bash
lsof -i :5001       # find the process holding the port
kill <PID>
```
Or simply use a different port: `--port 5002` (and update `PHASE_CONFIGS[1]`
in `computer/main.py` to match).

### 3. Computer says "Connect failed — retrying"
The emulator is not listening yet. Start the emulator first, wait for:
```
[EMU] Waiting for computer to connect...
```
Then start the computer. The computer retries every 3 s so order does not
matter in practice — just ensure both are running.

### 4. Frames arriving but `current_left`/`current_right` never change
The `control-loop` thread calls `SimulatedRobot.update()` at 50 Hz. If the
display shows `L=+0.00 R=+0.00` indefinitely after a CONTROL_REF is received:

a) Check `set_ref()` is being called — add a print in `_rx_loop` after decoding.
b) Check the `control-loop` thread is alive:
   ```python
   # add to robot_emulator.py temporarily
   for t in self._threads:
       print(f"{t.name} alive={t.is_alive()}")
   ```
c) Check `speed_ref != 0.0` — `_compute_targets` returns `(0, 0)` when
   `speed_ref == 0.0` regardless of angle.

### 5. CRC errors on received frames
If `--verbose` shows CRC errors on every CONTROL_REF frame, the protocol
constants in `emulator/src/protocol.py` differ from `computer/communication/protocol.py`.

Compare:
- Start bytes: both must be `0xCA 0xFE`
- End bytes: both must be `0xED 0xED`
- CRC polynomial: `0x1021`, initial `0x0000`, no reflection
- CRC input: `MSG_TYPE(1) + SEQ_NUM(2) + PAYLOAD_LEN(4) + PAYLOAD(N)`

Run the Python CRC on a known test vector to verify:
```python
from emulator.src.protocol import crc16
print(hex(crc16(b'\x01\x00\x00\x08\x00\x00\x00\x00\x00\x00\x0f')))
# must match the result from computer/communication/protocol.py:crc16
```

### 6. Emulator threads die silently
All threads are daemon threads — if an exception is raised inside one, it
silently exits and the display freezes. Wrap the loop body in a try/except to
surface errors:
```python
def _rx_loop(self) -> None:
    try:
        while ...:
            ...
    except Exception as exc:
        print(f"[ERROR] rx-loop crashed: {exc}")
        import traceback; traceback.print_exc()
```

## Invariants
- The emulator's `MSG_CONTROL_REF = 0x01`, `MSG_ACK = 0x02`, `MSG_HEARTBEAT = 0x03`
  must match `RobotMsg.*` in `computer/communication/protocol.py`.
- The `CONTROL_REF` payload is exactly 8 bytes (`<ff`). Any mismatch causes
  `decode_control_ref()` to silently read wrong values.
- `TcpLink.send()` is protected by `_tx_lock`. Never call `_conn.sendall()`
  directly from outside `TcpLink`.

## Verification
```bash
python emulator/src/main.py --port 5001 --verbose &
python -m computer.main --phase 1
# Press arrow up: emulator must show angle=0.0 speed=+1.00, L/R ramping up
# Release all keys: emulator must show speed=+0.00, L/R ramping to 0
```
