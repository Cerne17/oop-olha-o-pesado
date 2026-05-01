# Skill: Add a new message type to a link

## Objective
Introduce a new wire message type on Link A (CAM) or Link B (Robot) — for
example, a telemetry message, a configuration command, or a status report.

## Affected files
A message type touches **both ends of the link simultaneously**. Check which
link you are modifying:

| Link | Computer side | Firmware side | Emulator side |
|------|---------------|---------------|---------------|
| A (CAM) | `computer/communication/protocol.py` + `cam_receiver.py` | `cam/src/types/Protocol.h` + `CamComm.cpp` | N/A (CAM emulator not yet implemented) |
| B (Robot) | `computer/communication/protocol.py` + `robot_sender.py` | `robot/src/types/Protocol.h` + `RobotComm.cpp` | `emulator/src/protocol.py` + `robot_emulator.py` |

Also see the cross-cutting skill: `/sync-message-type`.

## Steps

### 1. Define the message type value
Open `computer/communication/protocol.py:31-41`. Add the new constant to the
appropriate namespace class:
```python
class RobotMsg:
    CONTROL_REF   = 0x01
    ACK           = 0x02
    HEARTBEAT     = 0x03
    MY_NEW_MSG    = 0x04   # <-- add here; pick next available value
```

### 2. Add a payload dataclass
After the existing payload classes (around line 120), add:
```python
@dataclass
class MyNewPayload:
    field_a: int    # uint16
    field_b: float  # float32

    SIZE: ClassVar[int] = 6
    _FMT: ClassVar[str] = '<Hf'

    def pack(self) -> bytes:
        return struct.pack(self._FMT, self.field_a, self.field_b)

    @classmethod
    def unpack(cls, data: bytes) -> MyNewPayload:
        a, b = struct.unpack_from(cls._FMT, data)
        return cls(a, b)
```
Use only little-endian struct format codes (`<`). Struct format reference:
`B`=uint8, `H`=uint16, `I`=uint32, `f`=float32, `d`=float64.

### 3. Add an encoder method to `FrameEncoder`
In `FrameEncoder` (`protocol.py:137`):
```python
def build_my_new_msg(self, seq: int, payload: MyNewPayload) -> bytes:
    return self.build(RobotMsg.MY_NEW_MSG, seq, payload.pack())
```

### 4. Add dispatch in the receiver or sender
**If the computer receives this message** (e.g. a telemetry reply from the
robot), add a branch in `CamReceiver._rx_loop` or `RobotSender._tx_loop`:
```python
elif t == RobotMsg.MY_NEW_MSG:
    if len(frame.payload) >= MyNewPayload.SIZE:
        p = MyNewPayload.unpack(frame.payload)
        # handle p
```

**If the computer sends this message**, call `_encoder.build_my_new_msg()`
from the appropriate TX path and write it to the transport.

### 5. Mirror the change in firmware (`Protocol.h`)
Open the correct firmware header. For Link B: `robot/src/types/Protocol.h`.
```cpp
enum class MsgType : uint8_t {
    CONTROL_REF = 0x01,
    ACK         = 0x02,
    HEARTBEAT   = 0x03,
    MY_NEW_MSG  = 0x04,   // <-- add here, value must match Python
};

struct MyNewPayload {
    uint16_t field_a;
    float    field_b;
} __attribute__((packed));
```

### 6. Dispatch in firmware (`RobotComm.cpp` or `CamComm.cpp`)
In `_dispatchFrame()`, add:
```cpp
case Protocol::MsgType::MY_NEW_MSG:
    if (_rx.payload_len == sizeof(Protocol::MyNewPayload)) {
        Protocol::MyNewPayload p;
        memcpy(&p, _payload_buf, sizeof(p));
        // handle p
    }
    break;
```

### 7. Mirror in emulator (Link B only)
Open `emulator/src/protocol.py` and add `MSG_MY_NEW_MSG = 0x04` plus a
`decode_my_new_msg()` method on `DecodedFrame`. Add a dispatch branch in
`robot_emulator.py:_rx_loop`.

## Invariants
- The numeric value of each message type must be **identical** in Python,
  C++ firmware, and the emulator. Mismatches cause silent type-dispatch errors.
- `_FMT` must use `<` (little-endian). The firmware uses `memcpy` into packed
  structs which are also little-endian on ESP32 (Xtensa is little-endian).
- Do not reuse or renumber existing message type values — the other end may
  already be deployed.
- `MAX_PAYLOAD` in `RobotComm.h:77` must be `>= sizeof(MyNewPayload)` after
  the change, otherwise the firmware will drop the new frames silently.

## Verification
1. Run Phase 1 with `--verbose` on the emulator and confirm the new type
   appears in the log.
2. Check `frame.crc_ok == True` on the first received frame of the new type.
3. Check no existing message types are broken (ACK and HEARTBEAT still work).
