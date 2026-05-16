# Skill: Use UDP transport for robot communication

## Objective
Switch Link B (Computer ↔ Robot) from Bluetooth/Serial to UDP over WiFi.
The wire protocol is identical — only the physical carrier changes.

## Key files
| File | Role |
|------|------|
| `computer/communication/transport.py` | `UDPTransport` implementation |
| `computer/main.py` | `_make_transport()` factory + `PHASE_CONFIGS` |
| `robot/src/communication/RobotComm.cpp` | ESP32 receive loop (needs WiFi port) |
| `SPEC.md §13` | UDP variant spec and firmware requirements |

---

## Computer side (already implemented)

`UDPTransport` is live. To activate it, edit the relevant `PhaseConfig` in
`computer/main.py`:

```python
2: PhaseConfig(
    robot_port      = "192.168.1.42:5005",   # ESP32 WiFi IP + listen port
    robot_transport = "udp",
    cam_port        = None,
),
```

`_make_transport` parses `"host:port"` automatically when `kind == "udp"`.

### local_port
By default `UDPTransport` binds to an ephemeral port (`local_port=0`).
If the ESP32 firmware sends ACK/HEARTBEAT frames back and needs a fixed
destination port on the computer side, pass `local_port` explicitly:

```python
# computer/main.py — _make_transport, "udp" branch
return UDPTransport(host, int(port_str), local_port=5006)
```

---

## ESP32 firmware side (requires manual porting)

Current `RobotComm` uses `BluetoothSerial`. Porting to WiFi+UDP:

### 1. Replace headers in `RobotComm.h`
```cpp
// Remove:
#include <BluetoothSerial.h>
// Add:
#include <WiFi.h>
#include <WiFiUdp.h>
```

Replace the `BluetoothSerial _bt` member with:
```cpp
WiFiUDP        _udp;
IPAddress      _client_ip;   // set on first received datagram
uint16_t       _client_port; // set on first received datagram
uint16_t       _listen_port;
```

### 2. Update `begin()` in `RobotComm.cpp`
```cpp
void RobotComm::begin() {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    while (WiFi.status() != WL_CONNECTED) { delay(500); }
    Serial.printf("[ROBOT] WiFi IP: %s\n", WiFi.localIP().toString().c_str());
    _udp.begin(_listen_port);

    xTaskCreatePinnedToCore(_udpTask,      "udp",     4096, this, 5, nullptr, 1);
    xTaskCreatePinnedToCore(_controlTask,  "control", 2048, this, 4, nullptr, 1);
    xTaskCreatePinnedToCore(_watchdogTask, "watchdog",2048, this, 3, nullptr, 1);
}
```

### 3. Replace `_btTask` with `_udpTask`
```cpp
void RobotComm::_udpTask(void* arg) {
    auto* self = static_cast<RobotComm*>(arg);
    uint8_t buf[256];

    for (;;) {
        int pkt_size = self->_udp.parsePacket();
        if (pkt_size > 0) {
            self->_client_ip   = self->_udp.remoteIP();
            self->_client_port = self->_udp.remotePort();
            int n = self->_udp.read(buf, sizeof(buf));
            for (int i = 0; i < n; i++) {
                self->_feedByte(buf[i]);
            }
        }
        vTaskDelay(pdMS_TO_TICKS(2));
    }
}
```

### 4. Replace `_bt.write()` in send helpers
```cpp
// _sendAck / _sendHeartbeat — replace:
_bt.write(out, len);
// with:
if (_client_port > 0) {
    _udp.beginPacket(_client_ip, _client_port);
    _udp.write(out, len);
    _udp.endPacket();
}
```

The frame format, CRC, `_feedByte`, `_dispatchFrame`, `_controlTask`, and
`_watchdogTask` are **unchanged**.

---

## Heartbeat requirement

Do **not** disable heartbeats. `RobotSender` sends `HEARTBEAT` at 1 Hz when
idle. Without it the ESP32 watchdog fires `emergencyStop()` after 5 s of
silence. At 20 Hz CONTROL_REF during active driving the watchdog is not at
risk, but heartbeats cover the idle case.

---

## Verification

```bash
# On the ESP32 serial monitor — confirm WiFi connected:
# [ROBOT] WiFi IP: 192.168.1.42

# Run Phase 2 with UDP config:
bash scripts/run.sh 2

# Expected:
# [ROBOT] Sender started
# (arrow keys move robot)
```

If frames arrive but the robot doesn't move, check that `_client_port > 0`
before the first `_sendAck` — the ESP32 learns the computer's address from the
first received datagram.
