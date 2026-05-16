# Handshake Buffer Overflow — Diagnosis (Revised)

**Symptom:** First BT/Serial connection causes "buffer overflow" and/or crash on the microcontroller.
**Scope:** `robot/src/communication/RobotComm.cpp`
**Method:** Python simulation of state machine + protocol byte trace (see below).

> **Original diagnosis was wrong on root cause.** Simulation proves no `_payload_buf`
> overflow exists at the application layer. The bug is a state machine resync failure
> triggered by BT connect-time noise, confirmed by producing 0 dispatches when 1 is expected.

---

## Root Cause Chain

```
BT connect
  → ESP32 SPP stack flushes negotiation bytes into BluetoothSerial 512 B FIFO
  → FIFO overflows (the "buffer overflow" the user observes)
  → Surviving bytes are garbage; state machine processes them
  → A 0xCA byte in garbage → state transitions to WAIT_START_2
  → First real frame arrives starting with 0xCA
  → WAIT_START_2 sees 0xCA ≠ 0xFE → goes to WAIT_START_1, drops 0xCA
  → Remaining frame bytes don't contain 0xCA 0xFE → frame missed entirely
  → _last_rx_ms never updated → watchdog fires at 5 s → emergencyStop()
```

---

## Bug 1 — WAIT_START_2 drops START_1 byte (CRITICAL — confirmed by simulation)

**File:** `RobotComm.cpp:101–106`
**Severity:** CRASH — directly causes first-frame loss after any noise

```cpp
case RxState::WAIT_START_2:
    _rx.state = (b == Protocol::FRAME_START_2)
                ? RxState::READ_HEADER
                : RxState::WAIT_START_1;   // ← drops b even if b == 0xCA
    _rx.bytes_read = 0;
    break;
```

When a stray `0xCA` byte (from BT noise or SPP negotiation) puts the state
machine into `WAIT_START_2`, the next real frame also starts with `0xCA`. That
`0xCA` fails the `== 0xFE` check and is dropped silently. The remaining frame
bytes contain no `0xCA 0xFE` pair, so the frame is never parsed.

**Simulation result:** with one preceding `0xCA` byte, a valid HEARTBEAT frame
produces 0 dispatches. With the fix applied, it produces 1.

**Fix:**

```cpp
case RxState::WAIT_START_2:
    _rx.bytes_read = 0;
    if (b == Protocol::FRAME_START_2) {
        _rx.state = RxState::READ_HEADER;
    } else if (b == Protocol::FRAME_START_1) {
        _rx.state = RxState::WAIT_START_2;  // re-arm: new START_1 received
    } else {
        _rx.state = RxState::WAIT_START_1;
    }
    break;
```

---

## Bug 2 — BluetoothSerial RX FIFO too small (the "buffer overflow" itself)

**File:** `RobotComm.cpp` (`begin()`)
**Severity:** OVERFLOW — the actual buffer that overflows; produces the garbage that triggers Bug 1

Default `BluetoothSerial` RX FIFO is 512 bytes. The ESP32 BT SPP stack pushes
profile negotiation frames into this buffer at connection time before any
application-level bytes arrive. If the negotiation data exceeds 512 bytes, the
FIFO overflows: older bytes are discarded and the received sequence is corrupted.

**Fix — increase FIFO before `begin()`:**

```cpp
void RobotComm::begin() {
    _bt.setRxBufferSize(4096);   // ← add before begin()
    _bt.begin(_bt_name);
    ...
}
```

---

## Bug 3 — WAIT_END_1 also drops START_1 byte (confirmed by simulation)

**File:** `RobotComm.cpp:148–152`
**Severity:** DESYNC — same class of bug as Bug 1, different state

```cpp
case RxState::WAIT_END_1:
    _rx.state = (b == Protocol::FRAME_END_1)
                ? RxState::WAIT_END_2
                : RxState::WAIT_START_1;   // drops b if b == 0xCA
    break;
```

If an unexpected byte arrives while waiting for `0xED` and that byte is `0xCA`
(START_1), the byte is dropped and the next frame's start is lost.

**Fix:**

```cpp
case RxState::WAIT_END_1:
    if (b == Protocol::FRAME_END_1) {
        _rx.state = RxState::WAIT_END_2;
    } else {
        _resetRx();
        if (b == Protocol::FRAME_START_1) _rx.state = RxState::WAIT_START_2;
    }
    break;
```

---

## Bug 4 — `memcpy(nullptr, 0)` in `_buildFrame` via `_sendHeartbeat`

**File:** `RobotComm.cpp:237`, `RobotComm.cpp:264–271`
**Severity:** UB — harmless on ESP32/GCC-Os in practice, but should be fixed

`_sendHeartbeat()` passes `nullptr` as the payload pointer:

```cpp
_buildFrame(Protocol::MsgType::HEARTBEAT, nullptr, 0, buf, sizeof(buf));
// inside _buildFrame:
memcpy(p, payload, payload_len);   // → memcpy(p, nullptr, 0)
```

C++ standard requires the pointer to be valid even when `n == 0`. On ESP32 with
GCC this is harmless (memcpy with n=0 exits immediately), but it is technically
undefined behaviour and GCC is permitted to miscompile it under `-O2`/`-Os`.

Note: `_dispatchFrame` line 176 uses `_rx.payload_buf` (a valid pointer), **not** `nullptr`.

**Fix — guard before the memcpy in `_buildFrame`:**

```cpp
if (payload && payload_len > 0)
    memcpy(p, payload, payload_len);
```

---

## Bug 5 — READ_PAYLOAD missing defensive upper-bound check

**File:** `RobotComm.cpp:133`
**Severity:** LATENT — guard in READ_HEADER prevents entry with bad `payload_len`,
but there is no second line of defence

```cpp
case RxState::READ_PAYLOAD:
    _rx.payload_buf[_rx.bytes_read++] = b;   // no bounds check
```

If `payload_len` were ever wrong (e.g. struct layout changes affecting Bug 6),
this overflows `_payload_buf[16]` into adjacent stack memory.

**Fix:**

```cpp
case RxState::READ_PAYLOAD:
    if (_rx.bytes_read >= MAX_PAYLOAD) { _resetRx(); return; }
    _rx.payload_buf[_rx.bytes_read++] = b;
```

---

## Bug 6 — READ_HEADER struct overlay (fragile, not currently broken)

**File:** `RobotComm.cpp:110`
**Severity:** FRAGILE — works today, silently breaks if struct is reordered

```cpp
uint8_t* hdr = reinterpret_cast<uint8_t*>(&_rx.msg_type);
hdr[_rx.bytes_read++] = b;   // writes into seq_num and payload_len bytes
```

The current `RxCtx` layout on ESP32 (32-bit) has no padding between `msg_type`,
`seq_num`, and `payload_len`, so this happens to be correct. If any field is
added before `payload_len`, padding appears and `payload_len` is parsed from
wrong bytes — the guard in READ_HEADER then passes a garbage value, enabling
Bug 5 to trigger.

The explicit unpack that follows is also redundant (the aliased writes via
`uint8_t*` already updated the struct fields; `uint8_t*` is aliasing-exempt).

**Fix — accumulate into a dedicated buffer, unpack explicitly:**

Add `uint8_t hdr_buf[7];` to `RxCtx`. Replace the overlay:

```cpp
case RxState::READ_HEADER: {
    _rx.hdr_buf[_rx.bytes_read++] = b;
    if (_rx.bytes_read == 7) {
        _rx.msg_type    = _rx.hdr_buf[0];
        _rx.seq_num     = (uint16_t)_rx.hdr_buf[1] | ((uint16_t)_rx.hdr_buf[2] << 8);
        _rx.payload_len = (uint32_t)_rx.hdr_buf[3]
                        | ((uint32_t)_rx.hdr_buf[4] << 8)
                        | ((uint32_t)_rx.hdr_buf[5] << 16)
                        | ((uint32_t)_rx.hdr_buf[6] << 24);
        _rx.bytes_read  = 0;
        if (_rx.payload_len > MAX_PAYLOAD) {
            _resetRx();
        } else {
            _rx.state = (_rx.payload_len > 0) ? RxState::READ_PAYLOAD : RxState::READ_CRC_LO;
        }
    }
    break;
}
```

---

## Priority order

| Priority | File | Location | Severity | Description |
|----------|------|----------|----------|-------------|
| 1 | RobotComm.cpp | `begin()` | OVERFLOW | BT FIFO 512 B → increase to 4096 |
| 2 | RobotComm.cpp | L101 | CRASH | WAIT_START_2 drops START_1 → first frame lost |
| 3 | RobotComm.cpp | L148 | DESYNC | WAIT_END_1 drops START_1 → cascading desync |
| 4 | RobotComm.cpp | L237 | UB | `memcpy(nullptr, 0)` in heartbeat path |
| 5 | RobotComm.cpp | L133 | LATENT | No upper bound in READ_PAYLOAD |
| 6 | RobotComm.cpp | L110 | FRAGILE | Struct overlay in READ_HEADER |

Fix priorities 1 and 2 first — they are the confirmed root-cause chain.
Priority 3 is the same class of bug as priority 2 and should be fixed in the same pass.

---

## What my original diagnosis got wrong

| Original claim | Actual finding |
|----------------|----------------|
| Bug 1: `_dispatchFrame` calls `memcpy(dst, nullptr, 0)` | `_dispatchFrame` uses `_rx.payload_buf` (valid ptr). Only `_buildFrame` via `_sendHeartbeat` has the nullptr. |
| Root cause: `_payload_buf` overflow | No `_payload_buf` overflow exists. Guard works. Simulation confirms. |
| Struct overlay causes misparse | Layout happens to be padding-free; unpack is correct today. Fragile, not broken. |
| Primary bug: `memcpy(nullptr,0)` | Confirmed harmless on platform. Not the crash. |
| **Missing entirely** | WAIT_START_2 resync failure — the actual cause, confirmed by simulation. |
