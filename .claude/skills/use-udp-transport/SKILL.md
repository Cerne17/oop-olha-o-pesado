---
name: use-udp-transport
description: Reference for UDP/WiFi transport used on both Link A (CAM→Computer) and Link B (Computer→Robot). Use when debugging UDP config, updating PHASE_CONFIGS IPs/ports, or reviewing the firmware UDP implementation.
---

# Skill: UDP transport for both links

Both links use UDP over WiFi. Wire protocol is identical — only the
physical carrier changed from Bluetooth/Serial.

## Current state

| Link | Direction | Transport | Port |
|------|-----------|-----------|------|
| A (CAM) | CAM → Computer | UDP/WiFi | CAM listens on 5006 |
| B (Robot) | Computer → Robot | UDP/WiFi | Robot listens on 5005 |

## Key files
| File | Role |
|------|------|
| `computer/communication/transport.py` | `UDPTransport` implementation |
| `computer/main.py` | `_make_transport()` factory + `PHASE_CONFIGS` |
| `robot/src/communication/RobotComm.cpp` | Link B — WiFiUDP receive loop |
| `cam/src/communication/CamComm.cpp` | Link A — WiFiUDP receive loop |

---

## Computer side

`UDPTransport` is live. Both phases 2 and 3 use it via `PHASE_CONFIGS`:

```python
2: PhaseConfig(
    robot_port      = "192.168.1.42:5005",
    robot_transport = "udp",
    cam_port        = None,
),
3: PhaseConfig(
    robot_port      = "192.168.1.42:5005",
    robot_transport = "udp",
    cam_port        = "192.168.1.43:5006",
    cam_transport   = "udp",
),
```

Update IPs to match what each board prints on boot:
```
[ROBOT] WiFi IP: 192.168.1.42
[CAM]   WiFi IP: 192.168.1.43
```

`_make_transport` parses `"host:port"` automatically when `kind == "udp"`.

---

## ESP32 firmware — address learning

Both boards are UDP servers. Neither knows the computer's address until the
first datagram arrives:

- **Robot**: learns `_client_ip` / `_client_port` from first received datagram
  in `_udpTask`. `_udpSend` silently drops until `_client_port > 0`.
- **CAM**: same pattern. `_client_known` flag gates `_cameraTask` — streaming
  does not start until first HEARTBEAT received.

The computer must send the first packet. `RobotSender` sends a `HEARTBEAT`
every 1 Hz when idle, which is sufficient.

---

## WiFi credentials

Both boards use gitignored `credentials.h` files:

```bash
cp robot/src/credentials.example.h robot/src/credentials.h
# edit: WIFI_SSID and WIFI_PASS
cd robot && pio run --target upload

cp cam/src/credentials.example.h cam/src/credentials.h
# edit: WIFI_SSID and WIFI_PASS
cd cam && pio run --target upload
```

`credentials.h` is in `.gitignore` — never commit it.

---

## Heartbeat requirement

Do **not** disable heartbeats. `RobotSender` sends `HEARTBEAT` at 1 Hz when
idle. Without it the ESP32 watchdog fires `emergencyStop()` after 5 s of
silence. The CAM also pauses streaming without a heartbeat reply.

---

## Verification

```bash
# Robot: confirm WiFi connected in serial monitor:
# [ROBOT] WiFi IP: 192.168.1.42
# [ROBOT] UDP listening on port 5005

# Run Phase 2:
bash scripts/run.sh 2
# Arrow keys should move robot; no watchdog stops in serial monitor

# Run Phase 3 with both boards:
bash scripts/run.sh 3
# Stats loop should show rx_frames and tx_frames increasing
```

If frames arrive but the robot doesn't move, check that `_client_port > 0`
before the first `_sendAck` — the ESP32 learns the computer's address from the
first received datagram.
