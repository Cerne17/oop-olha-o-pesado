# Skill: Extend the robot emulator with new mock behaviour

## Objective
Add new simulated behaviour to the robot emulator — for example, battery level
reporting, obstacle detection simulation, encoder feedback, or a configurable
physics model — without breaking the existing CONTROL_REF/ACK/HEARTBEAT loop.

## Key files
| File | Role |
|------|------|
| `emulator/src/robot_emulator.py` | Thread orchestrator — add new loops here |
| `emulator/src/simulated_robot.py` | Wheel model — extend the physics here |
| `emulator/src/protocol.py` | Add new message type constants and payload helpers |
| `emulator/src/tcp_link.py` | TX access — use `self._link.send()` only |

## Patterns

### Pattern A: New simulated state (no new message type)
Extend `SimulatedRobot` with new state and expose it in `snapshot()`.
The display loop in `robot_emulator.py:_display_loop` will pick it up.

Example — add simulated battery level:
```python
# simulated_robot.py
class SimulatedRobot:
    def __init__(self) -> None:
        ...
        self._battery: float = 1.0   # 0.0 = empty, 1.0 = full

    def update(self) -> None:
        with self._lock:
            ...
            # drain battery proportional to power draw
            power = (abs(self._current_left) + abs(self._current_right)) / 2.0
            self._battery = max(0.0, self._battery - power * 0.0001)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                ...,
                'battery': self._battery,
            }
```
Then update `_display_loop` in `robot_emulator.py` to print `s['battery']`.

### Pattern B: New outbound message (emulator → computer)
For mock data the computer needs to receive (telemetry, status), add a new
message type using `/sync-message-type` and then:

1. Add `MSG_MY_STATUS = 0x04` to `emulator/src/protocol.py`.
2. Add `build_my_status()` to `FrameEncoder`.
3. Add a new loop thread in `robot_emulator.py`:
```python
def _status_loop(self) -> None:
    while not self._stop_event.is_set() and self._link.is_connected:
        s = self._robot.snapshot()
        frame = self._encoder.build_my_status(self._next_seq(), s['battery'])
        self._send(frame)
        time.sleep(2.0)
```
4. Append the thread in `run()`:
```python
threading.Thread(target=self._status_loop, name="emu-status", daemon=True),
```

### Pattern C: New inbound message (computer → emulator)
Add a dispatch branch in `_rx_loop` of `robot_emulator.py`:
```python
elif t == MSG_MY_COMMAND:
    if len(frame.payload) >= MyCommandPayload.SIZE:
        cmd = frame.decode_my_command()
        self._robot.apply_command(cmd)
        ack = self._encoder.build_ack(self._next_seq(), frame.seq_num, status=0)
        self._send(ack)
```

## Invariants
- All TX calls must go through `self._send()` (which calls `self._link.send()`
  with the internal `_tx_lock`). Never call `self._link._conn.sendall()` directly.
- Do not add blocking calls inside thread loops. Use `time.sleep()` for pacing
  and check `self._stop_event.is_set()` at the top of every iteration.
- Keep `simulated_robot.py:_compute_targets` and `_slew` unchanged unless you
  are intentionally changing the physics model. They mirror the real firmware.
- Any new message type value must not clash with existing values:
  `CONTROL_REF=0x01`, `ACK=0x02`, `HEARTBEAT=0x03`.

## Verification
Add a print in the new loop and run:
```bash
python emulator/src/main.py --verbose
python -m computer.main --phase 1
# Observe the new message type in the verbose output
```
