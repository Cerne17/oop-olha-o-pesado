# Skill: Debug UDP transport issues

## Objective
Diagnose failures when using `UDPTransport` between the computer and the ESP32
over WiFi. Covers: no connection, missing frames, watchdog fires, CRC errors,
and port/firewall issues.

## Key files
| File | Role |
|------|------|
| `computer/communication/transport.py` | `UDPTransport` — socket bind, send, recv |
| `computer/communication/robot_sender.py` | `_tx_loop` — send rate, heartbeat logic |
| `computer/communication/protocol.py` | Frame encoder/decoder, CRC |
| `robot/src/communication/RobotComm.cpp` | ESP32 receive loop, watchdog reset |

---

## Step 1 — Confirm UDP socket is bound

Add a temporary print in `UDPTransport.connect()`:
```python
sock.bind(("", self._local_port))
print(f"[UDP] bound to {sock.getsockname()}")
```
If `connect()` raises `ConnectionError: bind failed`, the local port is in use.
Fix: pass `local_port=0` to let the OS assign an ephemeral port.

---

## Step 2 — Confirm datagrams reach the ESP32

On the computer, send a test datagram with `nc` before running the full stack:
```bash
echo -n "" | nc -u 192.168.1.42 5005
```
On the ESP32 serial monitor, add a temporary log in `_udpTask`:
```cpp
if (pkt_size > 0) {
    Serial.printf("[UDP] recv %d bytes from %s:%d\n",
        pkt_size,
        self->_udp.remoteIP().toString().c_str(),
        self->_udp.remotePort());
}
```
If nothing prints, the packet is being dropped. Check:
- WiFi signal strength (`WiFi.RSSI()` in firmware).
- Firewall on the computer (`sudo pfctl -d` on macOS to temporarily disable).
- Correct IP and port in `PhaseConfig.robot_port`.

---

## Step 3 — Confirm frames are well-formed (CRC errors)

On the computer side, dump the raw bytes of a CONTROL_REF frame:
```python
from computer.communication.protocol import FrameEncoder, ControlRefPayload
enc = FrameEncoder()
frame = enc.build_control_ref(0, ControlRefPayload(0.0, 0.5))
print(frame.hex())
# Expected start: cafe 01 0000 08000000 ...
```

On the ESP32, log the raw bytes received in `_feedByte` for the first few calls
to confirm the frame boundaries are intact across a single datagram.

`receive_available()` returns one full datagram per call — the `FrameDecoder`
scans for `0xCA 0xFE` start bytes, so partial frames are handled correctly as
long as each datagram contains at most one frame (which `send()` guarantees
since `sendto()` is atomic).

---

## Step 4 — Watchdog fires unexpectedly

**Symptom:** Robot stops after ~5 s even while driving.

Cause A — heartbeat not reaching ESP32: check Step 2 above; the 1 Hz heartbeat
uses the same `send()` path as CONTROL_REF.

Cause B — ESP32 never updates `_last_rx_ms`: this field is only set in
`_dispatchFrame()` after a frame passes CRC. Add a log there:
```cpp
void RobotComm::_dispatchFrame() {
    // ... existing CRC check ...
    if (!crc_ok) { Serial.println("[ROBOT] CRC FAIL"); return; }
    _last_rx_ms = millis();   // <-- add log here
    Serial.println("[ROBOT] frame ok, watchdog reset");
    // ...
}
```

Cause C — NAT / router drops UDP after idle: some routers close UDP sessions
after 30 s. The 1 Hz heartbeat keeps the session alive; if the router timeout
is shorter, reduce heartbeat interval in `RobotSender` or configure the router.

---

## Step 5 — Robot receives frames but doesn't respond (no ACK back)

The ESP32 learns the computer's IP and port from the **first received datagram**:
```cpp
self->_client_ip   = self->_udp.remoteIP();
self->_client_port = self->_udp.remotePort();
```
If `_client_port == 0` when `_sendAck` / `_sendHeartbeat` runs, the reply is
silently dropped. Ensure at least one datagram has been received before
expecting replies.

The computer-side `RobotSender` does not currently consume ACK frames —
missing ACKs won't stall the sender but they can mask firmware-side issues.

---

## Step 6 — High packet loss / jitter

UDP is unreliable. At 20 Hz, one dropped CONTROL_REF is not critical — the
watchdog is 5 s and the next frame arrives in 50 ms. But sustained loss (>50%)
will cause jerky motion.

Diagnose with:
```bash
# Ping to check base latency + loss:
ping -c 50 192.168.1.42

# Watch tx_frames counter climb at ~20/s:
# Add to RobotSender.stats() call site in main.py:
print(robot_sender.stats())
```

Fix: move the ESP32 closer to the router, or switch to the 2.4 GHz band
(better range than 5 GHz through walls).

---

## Step 7 — "UDPTransport: not connected" at send time

`is_connected()` returns `True` as soon as the socket is bound — there is no
handshake. If you see this error, `disconnect()` was called before `send()`.
Check thread lifecycle: `RobotSender.stop()` calls `disconnect()` after the
tx thread joins.

---

## Quick checklist

| Check | Command / location |
|-------|--------------------|
| ESP32 WiFi up | Serial monitor: `[ROBOT] WiFi IP: x.x.x.x` |
| Correct IP+port | `PHASE_CONFIGS[N].robot_port` in `computer/main.py` |
| Socket bound | Log in `UDPTransport.connect()` |
| Datagrams arrive at ESP32 | Log in `_udpTask` |
| CRC passing | Log in `_dispatchFrame` |
| Watchdog reset seen | Log `_last_rx_ms = millis()` |
| No firewall blocking UDP | `sudo pfctl -d` (macOS) |
