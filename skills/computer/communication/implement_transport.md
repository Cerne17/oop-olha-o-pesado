# Skill: Implement a new Transport strategy

## Objective
Add a new concrete `Transport` subclass (e.g. WebSocket, UDP, Unix socket) so
that `CamReceiver` and `RobotSender` can operate over a new link type without
any changes to those classes.

## Key files
| File | Role |
|------|------|
| `computer/types/transport.py` | `Transport` ABC — the contract to implement |
| `computer/communication/transport.py` | Existing concrete implementations (reference) |
| `computer/main.py` | `_make_transport()` factory + `PHASE_CONFIGS` |

## Reference implementation
`TCPTransport` at the bottom of `computer/communication/transport.py` is the
simplest existing example. Read it before writing a new transport.

## Steps

### 1. Read the ABC
Open `computer/types/transport.py`. The five methods you must implement:
```
connect()                          -> None   raise ConnectionError on failure
disconnect()                       -> None
send(data: bytes)                  -> None   raise ConnectionError on failure
receive_available(max_bytes: int)  -> bytes  return b'' when no data; non-blocking
is_connected()                     -> bool
```

### 2. Add the class to `computer/communication/transport.py`
Append after the last class. Follow the pattern:
```python
class MyTransport(Transport):
    def __init__(self, ...) -> None:
        ...
        self._tx_lock = threading.Lock()   # always include a TX lock

    def connect(self) -> None:
        # open / connect the resource
        # raise ConnectionError on failure

    def disconnect(self) -> None:
        # close the resource; swallow OSError

    def send(self, data: bytes) -> None:
        with self._tx_lock:
            if not self._resource:
                raise ConnectionError("MyTransport: not connected")
            try:
                # write data
            except OSError as exc:
                raise ConnectionError(...) from exc

    def receive_available(self, max_bytes: int = 4096) -> bytes:
        if not self._resource:
            return b''
        try:
            # non-blocking read
            return ...
        except BlockingIOError:
            return b''
        except OSError as exc:
            raise ConnectionError(...) from exc

    def is_connected(self) -> bool:
        return self._resource is not None
```

### 3. Register in `_make_transport()` (`computer/main.py:62`)
```python
if kind == "my_transport":
    return MyTransport(...)
```
Parse any extra parameters from the `port` string (e.g. `"host:port"` split on `:`).

### 4. Add a `PhaseConfig` entry if needed
In `PHASE_CONFIGS` (`computer/main.py:45`) add or update the phase config:
```python
N: PhaseConfig(
    robot_port      = "...",
    robot_transport = "my_transport",
    ...
),
```

### 5. Export from the module (optional)
If external code needs to import the new class directly, add it to
`computer/communication/__init__.py` if that file exists, or document the
import path in a docstring.

## Invariants
- `receive_available()` MUST be non-blocking. `CamReceiver._rx_loop` and
  `RobotSender._tx_loop` call it in tight loops with only a 5 ms sleep when
  `b''` is returned.
- `send()` MUST be thread-safe (protected by `_tx_lock`). Both loops can call
  `send()` from different threads simultaneously in future.
- All I/O errors must be converted to `ConnectionError` — the receiver/sender
  only catch `ConnectionError` to trigger reconnect.
- Do NOT touch `CamReceiver`, `RobotSender`, or any observer code.

## Verification
```bash
# Swap Phase 1 to your transport, run the emulator counterpart, and verify:
python -m computer.main --phase 1
# Stats loop must show rx_frames and tx_frames increasing
```
