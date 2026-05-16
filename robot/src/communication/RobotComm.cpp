#include "RobotComm.h"
#include "credentials.h"
#include <string.h>

// =============================================================================
// RobotComm — implementation
// =============================================================================

RobotComm::RobotComm(WheelController& wheel, uint16_t listen_port)
    : _wheel(wheel), _listen_port(listen_port)
{
    _tx_mutex = xSemaphoreCreateMutex();
}

void RobotComm::begin() {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("[ROBOT] Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\n[ROBOT] WiFi IP: %s\n", WiFi.localIP().toString().c_str());

    _udp.begin(_listen_port);
    Serial.printf("[ROBOT] UDP listening on port %u\n", _listen_port);

    xTaskCreatePinnedToCore(_udpTask,      "udp",     4096, this, 5, nullptr, 1);
    xTaskCreatePinnedToCore(_controlTask,  "control", 2048, this, 4, nullptr, 1);
    xTaskCreatePinnedToCore(_watchdogTask, "watchdog",2048, this, 3, nullptr, 1);
}

// ---------------------------------------------------------------------------
// UDP task — receive + dispatch
// ---------------------------------------------------------------------------

void RobotComm::_udpTask(void* arg) {
    auto* self = static_cast<RobotComm*>(arg);
    uint8_t  buf[256];
    uint32_t last_hb_ms = 0;

    for (;;) {
        int pkt_size = self->_udp.parsePacket();
        if (pkt_size > 0) {
            // Record sender address so replies go to the right host/port.
            self->_client_ip   = self->_udp.remoteIP();
            self->_client_port = self->_udp.remotePort();

            int n = self->_udp.read(buf, sizeof(buf));
            for (int i = 0; i < n; i++) {
                self->_feedByte(buf[i]);
            }
        }

        // Send periodic heartbeat so the computer-side watchdog stays alive.
        uint32_t now = millis();
        if (now - last_hb_ms >= 1000) {
            self->_sendHeartbeat();
            last_hb_ms = now;
        }

        vTaskDelay(pdMS_TO_TICKS(2));
    }
}

// ---------------------------------------------------------------------------
// Control task — smooth-motion loop at CONTROL_HZ
// ---------------------------------------------------------------------------

void RobotComm::_controlTask(void* arg) {
    auto* self = static_cast<RobotComm*>(arg);
    const TickType_t period = pdMS_TO_TICKS(
        1000 / WheelController::CONTROL_HZ
    );
    TickType_t last_wake = xTaskGetTickCount();

    for (;;) {
        self->_wheel.update();
        vTaskDelayUntil(&last_wake, period);
    }
}

// ---------------------------------------------------------------------------
// Watchdog task — emergency stop on link loss
// ---------------------------------------------------------------------------

void RobotComm::_watchdogTask(void* arg) {
    auto* self = static_cast<RobotComm*>(arg);

    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(500));
        if (self->_last_rx_ms > 0 &&
            millis() - self->_last_rx_ms > WATCHDOG_TIMEOUT_MS)
        {
            Serial.println("[ROBOT] Watchdog: link lost — emergency stop");
            self->_wheel.emergencyStop();
            self->_last_rx_ms = millis();  // prevent repeated log spam
        }
    }
}

// ---------------------------------------------------------------------------
// Frame decoder state machine
// ---------------------------------------------------------------------------

void RobotComm::_resetRx() {
    _rx.state       = RxState::WAIT_START_1;
    _rx.bytes_read  = 0;
    _rx.payload_len = 0;
}

void RobotComm::_feedByte(uint8_t b) {
    switch (_rx.state) {

    case RxState::WAIT_START_1:
        if (b == Protocol::FRAME_START_1) _rx.state = RxState::WAIT_START_2;
        break;

    case RxState::WAIT_START_2:
        _rx.bytes_read = 0;
        if (b == Protocol::FRAME_START_2) {
            _rx.state = RxState::READ_HEADER;
        } else if (b == Protocol::FRAME_START_1) {
            // Another 0xCA arrived before 0xFE — re-arm rather than discard.
            // Dropping it (going to WAIT_START_1) would cause the next frame's
            // opening byte to be lost. See DIAGNOSIS.md §Bug 1.
            _rx.state = RxState::WAIT_START_2;
        } else {
            _rx.state = RxState::WAIT_START_1;
        }
        break;

    case RxState::READ_HEADER: {
        // Accumulate the 7-byte wire header into hdr_buf, then unpack
        // explicitly.  Wire layout (little-endian):
        //   [0]      msg_type  (1 B)
        //   [1..2]   seq_num   (2 B LE)
        //   [3..6]   payload_len (4 B LE)
        _rx.hdr_buf[_rx.bytes_read++] = b;
        if (_rx.bytes_read == 7) {
            _rx.msg_type    = _rx.hdr_buf[0];
            _rx.seq_num     = (uint16_t)_rx.hdr_buf[1]
                            | ((uint16_t)_rx.hdr_buf[2] << 8);
            _rx.payload_len = (uint32_t)_rx.hdr_buf[3]
                            | ((uint32_t)_rx.hdr_buf[4] << 8)
                            | ((uint32_t)_rx.hdr_buf[5] << 16)
                            | ((uint32_t)_rx.hdr_buf[6] << 24);
            _rx.bytes_read  = 0;
            if (_rx.payload_len > MAX_PAYLOAD) {
                _resetRx();
            } else {
                _rx.state = (_rx.payload_len > 0)
                             ? RxState::READ_PAYLOAD
                             : RxState::READ_CRC_LO;
            }
        }
        break;
    }

    case RxState::READ_PAYLOAD:
        // Defensive bound — payload_len is validated in READ_HEADER, but a
        // second check here ensures a logic error can never smash adjacent memory.
        if (_rx.bytes_read >= MAX_PAYLOAD) { _resetRx(); return; }
        _payload_buf[_rx.bytes_read++] = b;
        if (_rx.bytes_read == _rx.payload_len)
            _rx.state = RxState::READ_CRC_LO;
        break;

    case RxState::READ_CRC_LO:
        _rx.crc_rx  = b;
        _rx.state   = RxState::READ_CRC_HI;
        break;

    case RxState::READ_CRC_HI:
        _rx.crc_rx |= (uint16_t)b << 8;
        _rx.state   = RxState::WAIT_END_1;
        break;

    case RxState::WAIT_END_1:
        if (b == Protocol::FRAME_END_1) {
            _rx.state = RxState::WAIT_END_2;
        } else {
            // Unexpected byte — discard this frame. Re-arm if the byte is a
            // frame start so the next 0xFE is not lost. See DIAGNOSIS.md §Bug 3.
            _resetRx();
            if (b == Protocol::FRAME_START_1) _rx.state = RxState::WAIT_START_2;
        }
        break;

    case RxState::WAIT_END_2:
        if (b == Protocol::FRAME_END_2)
            _dispatchFrame();
        _resetRx();
        break;
    }
}

void RobotComm::_dispatchFrame() {
    // Verify CRC
    uint8_t hdr_for_crc[7];
    hdr_for_crc[0] = _rx.msg_type;
    hdr_for_crc[1] = (uint8_t)(_rx.seq_num);
    hdr_for_crc[2] = (uint8_t)(_rx.seq_num >> 8);
    hdr_for_crc[3] = (uint8_t)(_rx.payload_len);
    hdr_for_crc[4] = (uint8_t)(_rx.payload_len >> 8);
    hdr_for_crc[5] = (uint8_t)(_rx.payload_len >> 16);
    hdr_for_crc[6] = (uint8_t)(_rx.payload_len >> 24);

    // Recompute over full header+payload
    uint8_t crc_input[7 + MAX_PAYLOAD];
    memcpy(crc_input, hdr_for_crc, 7);
    memcpy(crc_input + 7, _payload_buf, _rx.payload_len);
    uint16_t computed_crc = Protocol::crc16(crc_input, 7 + _rx.payload_len);

    if (computed_crc != _rx.crc_rx) {
        _sendAck(_rx.seq_num, 1);  // CRC_ERROR
        return;
    }

    _last_rx_ms = millis();

    switch (static_cast<Protocol::MsgType>(_rx.msg_type)) {

    case Protocol::MsgType::CONTROL_REF:
        if (_rx.payload_len == sizeof(Protocol::ControlRefPayload)) {
            Protocol::ControlRefPayload ref;
            memcpy(&ref, _payload_buf, sizeof(ref));
            _wheel.setRef(ref);
            _sendAck(_rx.seq_num, 0);  // OK
        }
        break;

    case Protocol::MsgType::HEARTBEAT:
        _sendHeartbeat();
        break;

    case Protocol::MsgType::ACK:
        break;  // robot doesn't act on incoming ACKs

    default:
        _sendAck(_rx.seq_num, 2);  // UNKNOWN_TYPE
        break;
    }
}

// ---------------------------------------------------------------------------
// Frame building
// ---------------------------------------------------------------------------

size_t RobotComm::_buildFrame(Protocol::MsgType type,
                               const uint8_t* payload, size_t payload_len,
                               uint8_t* out, size_t out_size) {
    size_t total = Protocol::OVERHEAD + payload_len;
    if (out_size < total) return 0;

    uint8_t* p = out;

    // Start magic
    *p++ = Protocol::FRAME_START_1;
    *p++ = Protocol::FRAME_START_2;

    // CRC input region starts here
    uint8_t* crc_start = p;

    *p++ = static_cast<uint8_t>(type);
    *p++ = (uint8_t)(_tx_seq);
    *p++ = (uint8_t)(_tx_seq >> 8);
    *p++ = (uint8_t)(payload_len);
    *p++ = (uint8_t)(payload_len >> 8);
    *p++ = (uint8_t)(payload_len >> 16);
    *p++ = (uint8_t)(payload_len >> 24);

    // Guard against null: memcpy(dst, nullptr, 0) is undefined behaviour even
    // when n == 0.  HEARTBEAT frames have no payload and pass nullptr here.
    if (payload && payload_len > 0) {
        memcpy(p, payload, payload_len);
    }
    p += payload_len;

    uint16_t crc = Protocol::crc16(crc_start, 7 + payload_len);
    *p++ = (uint8_t)(crc);
    *p++ = (uint8_t)(crc >> 8);

    // End magic
    *p++ = Protocol::FRAME_END_1;
    *p++ = Protocol::FRAME_END_2;

    _tx_seq++;
    return total;
}

void RobotComm::_sendAck(uint16_t acked_seq, uint8_t status) {
    Protocol::AckPayload ack { acked_seq, status };
    uint8_t buf[Protocol::OVERHEAD + sizeof(ack)];
    size_t len = _buildFrame(Protocol::MsgType::ACK,
                             reinterpret_cast<const uint8_t*>(&ack),
                             sizeof(ack), buf, sizeof(buf));
    if (len == 0) return;
    _udpSend(buf, len);
}

void RobotComm::_sendHeartbeat() {
    uint8_t buf[Protocol::OVERHEAD];
    size_t len = _buildFrame(Protocol::MsgType::HEARTBEAT,
                             nullptr, 0, buf, sizeof(buf));
    if (len == 0) return;
    _udpSend(buf, len);
}

void RobotComm::_udpSend(const uint8_t* data, size_t len) {
    // No destination known yet — first datagram from the computer sets _client_port.
    if (_client_port == 0) return;
    xSemaphoreTake(_tx_mutex, portMAX_DELAY);
    _udp.beginPacket(_client_ip, _client_port);
    _udp.write(data, len);
    _udp.endPacket();
    xSemaphoreGive(_tx_mutex);
}
