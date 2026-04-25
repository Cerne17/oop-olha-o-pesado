#include "RobotComm.h"
#include <string.h>

// =============================================================================
// RobotComm — implementation
// =============================================================================

RobotComm::RobotComm(WheelController& wheel, const char* bt_name)
    : _wheel(wheel), _bt_name(bt_name)
{
    _tx_mutex = xSemaphoreCreateMutex();
    _rx.payload_buf = _payload_buf;
}

void RobotComm::begin() {
    _bt.begin(_bt_name);
    Serial.printf("[ROBOT] Bluetooth started as '%s'\n", _bt_name);

    xTaskCreatePinnedToCore(_btTask,       "bt",      4096, this, 5, nullptr, 1);
    xTaskCreatePinnedToCore(_controlTask,  "control", 2048, this, 4, nullptr, 1);
    xTaskCreatePinnedToCore(_watchdogTask, "watchdog",2048, this, 3, nullptr, 1);
}

// ---------------------------------------------------------------------------
// BT task — receive + dispatch
// ---------------------------------------------------------------------------

void RobotComm::_btTask(void* arg) {
    auto* self = static_cast<RobotComm*>(arg);
    uint32_t last_hb_ms = 0;

    for (;;) {
        while (self->_bt.available()) {
            self->_feedByte((uint8_t)self->_bt.read());
        }

        // Send periodic heartbeat
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
        _rx.state = (b == Protocol::FRAME_START_2)
                    ? RxState::READ_HEADER
                    : RxState::WAIT_START_1;
        _rx.bytes_read = 0;
        break;

    case RxState::READ_HEADER: {
        // Header: type(1) + seq(2) + len(4) = 7 bytes
        uint8_t* hdr = reinterpret_cast<uint8_t*>(&_rx.msg_type);
        hdr[_rx.bytes_read++] = b;
        if (_rx.bytes_read == 7) {
            // Unpack little-endian seq and len from raw bytes
            _rx.seq_num     = (uint16_t)hdr[1] | ((uint16_t)hdr[2] << 8);
            _rx.payload_len = (uint32_t)hdr[3]        |
                              ((uint32_t)hdr[4] << 8)  |
                              ((uint32_t)hdr[5] << 16) |
                              ((uint32_t)hdr[6] << 24);
            _rx.msg_type    = hdr[0];
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
        _rx.payload_buf[_rx.bytes_read++] = b;
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
        _rx.state = (b == Protocol::FRAME_END_1)
                    ? RxState::WAIT_END_2
                    : RxState::WAIT_START_1;
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

    uint16_t crc = Protocol::crc16(hdr_for_crc, 7);
    crc = Protocol::crc16(_rx.payload_buf, _rx.payload_len);

    // Recompute over full header+payload
    uint8_t crc_input[7 + MAX_PAYLOAD];
    memcpy(crc_input, hdr_for_crc, 7);
    memcpy(crc_input + 7, _rx.payload_buf, _rx.payload_len);
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
            memcpy(&ref, _rx.payload_buf, sizeof(ref));
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

    memcpy(p, payload, payload_len);
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
    xSemaphoreTake(_tx_mutex, portMAX_DELAY);
    _bt.write(buf, len);
    xSemaphoreGive(_tx_mutex);
}

void RobotComm::_sendHeartbeat() {
    uint8_t buf[Protocol::OVERHEAD];
    size_t len = _buildFrame(Protocol::MsgType::HEARTBEAT,
                             nullptr, 0, buf, sizeof(buf));
    if (len == 0) return;
    xSemaphoreTake(_tx_mutex, portMAX_DELAY);
    _bt.write(buf, len);
    xSemaphoreGive(_tx_mutex);
}
