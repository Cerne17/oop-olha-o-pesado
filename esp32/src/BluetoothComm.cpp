#include "BluetoothComm.h"
#include <string.h>

// ---------------------------------------------------------------------------
// Construction
// ---------------------------------------------------------------------------
BluetoothComm::BluetoothComm(const char* device_name)
    : _device_name(device_name)
{
    _tx_mutex = xSemaphoreCreateMutex();
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
bool BluetoothComm::begin() {
    if (!_bt.begin(_device_name)) {
        Serial.println("[BT] Failed to start BluetoothSerial");
        return false;
    }
    Serial.printf("[BT] Advertising as '%s'\n", _device_name);
    return true;
}

void BluetoothComm::end() {
    _bt.end();
    if (_rx_payload_buf) {
        free(_rx_payload_buf);
        _rx_payload_buf = nullptr;
    }
}

// ---------------------------------------------------------------------------
// Receiving — public poll()
// ---------------------------------------------------------------------------
void BluetoothComm::poll() {
    while (_bt.available()) {
        _processReceivedByte(static_cast<uint8_t>(_bt.read()));
    }
}

// ---------------------------------------------------------------------------
// Receive state machine
// ---------------------------------------------------------------------------
void BluetoothComm::_processReceivedByte(uint8_t b) {
    // A small inline header buffer so we can read type+seq+len sequentially.
    static uint8_t hdr_buf[7];  // type(1)+seq_lo+seq_hi+len(4)

    switch (_rx_state) {

    case RxState::WAIT_START_1:
        if (b == Protocol::FRAME_START_1) _rx_state = RxState::WAIT_START_2;
        break;

    case RxState::WAIT_START_2:
        if (b == Protocol::FRAME_START_2) {
            _rx_bytes_read = 0;
            _rx_state = RxState::READ_HEADER;
        } else {
            _rx_state = RxState::WAIT_START_1;
        }
        break;

    case RxState::READ_HEADER:
        hdr_buf[_rx_bytes_read++] = b;
        if (_rx_bytes_read == 7) {
            _rx_type = hdr_buf[0];
            _rx_seq  = static_cast<uint16_t>(hdr_buf[1]) |
                       (static_cast<uint16_t>(hdr_buf[2]) << 8);
            _rx_len  = static_cast<uint32_t>(hdr_buf[3])        |
                       (static_cast<uint32_t>(hdr_buf[4]) << 8)  |
                       (static_cast<uint32_t>(hdr_buf[5]) << 16) |
                       (static_cast<uint32_t>(hdr_buf[6]) << 24);

            // Sanity check — reject absurdly large frames (>64 KB)
            if (_rx_len > 65536) {
                Serial.printf("[BT] RX: implausible payload length %u, resetting\n", _rx_len);
                _rx_error_count++;
                _resetRx();
                break;
            }

            // Allocate (or reallocate) the payload buffer
            if (_rx_payload_buf) free(_rx_payload_buf);
            _rx_payload_buf = static_cast<uint8_t*>(malloc(_rx_len == 0 ? 1 : _rx_len));
            if (!_rx_payload_buf) {
                Serial.println("[BT] RX: malloc failed, resetting");
                _rx_error_count++;
                _resetRx();
                break;
            }

            _rx_bytes_read = 0;
            _rx_state = (_rx_len > 0) ? RxState::READ_PAYLOAD : RxState::READ_CRC_1;
        }
        break;

    case RxState::READ_PAYLOAD:
        _rx_payload_buf[_rx_bytes_read++] = b;
        if (_rx_bytes_read == _rx_len) {
            _rx_state = RxState::READ_CRC_1;
        }
        break;

    case RxState::READ_CRC_1:
        _rx_crc = static_cast<uint16_t>(b);
        _rx_state = RxState::READ_CRC_2;
        break;

    case RxState::READ_CRC_2:
        _rx_crc |= static_cast<uint16_t>(b) << 8;
        _rx_state = RxState::WAIT_END_1;
        break;

    case RxState::WAIT_END_1:
        if (b == Protocol::FRAME_END_1) {
            _rx_state = RxState::WAIT_END_2;
        } else {
            Serial.println("[BT] RX: missing end marker 1, resetting");
            _rx_error_count++;
            _resetRx();
        }
        break;

    case RxState::WAIT_END_2:
        if (b == Protocol::FRAME_END_2) {
            _dispatchFrame();
        } else {
            Serial.println("[BT] RX: missing end marker 2, resetting");
            _rx_error_count++;
        }
        _resetRx();
        break;
    }
}

void BluetoothComm::_dispatchFrame() {
    // Build the CRC input buffer: type(1) + seq(2) + len(4) + payload(N)
    size_t crc_input_len = 7 + _rx_len;
    uint8_t* crc_buf = static_cast<uint8_t*>(malloc(crc_input_len));
    if (!crc_buf) {
        _rx_error_count++;
        return;
    }

    crc_buf[0] = _rx_type;
    crc_buf[1] = static_cast<uint8_t>(_rx_seq);
    crc_buf[2] = static_cast<uint8_t>(_rx_seq >> 8);
    crc_buf[3] = static_cast<uint8_t>(_rx_len);
    crc_buf[4] = static_cast<uint8_t>(_rx_len >> 8);
    crc_buf[5] = static_cast<uint8_t>(_rx_len >> 16);
    crc_buf[6] = static_cast<uint8_t>(_rx_len >> 24);
    if (_rx_len > 0) memcpy(crc_buf + 7, _rx_payload_buf, _rx_len);

    uint16_t computed = Protocol::crc16(crc_buf, crc_input_len);
    free(crc_buf);

    if (computed != _rx_crc) {
        Serial.printf("[BT] RX: CRC mismatch (got 0x%04X, expected 0x%04X)\n",
                      _rx_crc, computed);
        _rx_error_count++;
        // Send a NACK
        sendAck(_rx_seq, 1);
        return;
    }

    _rx_frame_count++;

    // Dispatch to registered callback
    auto it = _callbacks.find(_rx_type);
    if (it != _callbacks.end()) {
        it->second(_rx_payload_buf, _rx_len);
    } else {
        Serial.printf("[BT] RX: no handler for type 0x%02X\n", _rx_type);
    }
}

void BluetoothComm::_resetRx() {
    _rx_state      = RxState::WAIT_START_1;
    _rx_bytes_read = 0;
    _rx_len        = 0;
}

// ---------------------------------------------------------------------------
// Sending
// ---------------------------------------------------------------------------
size_t BluetoothComm::_buildFrame(Protocol::MsgType type,
                                   const uint8_t* payload, size_t payload_len,
                                   uint8_t* out, size_t out_size)
{
    size_t total = Protocol::OVERHEAD + payload_len;
    if (total > out_size) return 0;

    uint8_t t = static_cast<uint8_t>(type);

    // Advance sequence number
    uint16_t seq = _tx_seq++;

    // Build CRC input: type(1) + seq(2) + len(4) + payload(N)
    size_t crc_len = 7 + payload_len;
    uint8_t* crc_buf = static_cast<uint8_t*>(alloca(crc_len));
    crc_buf[0] = t;
    crc_buf[1] = static_cast<uint8_t>(seq);
    crc_buf[2] = static_cast<uint8_t>(seq >> 8);
    crc_buf[3] = static_cast<uint8_t>(payload_len);
    crc_buf[4] = static_cast<uint8_t>(payload_len >> 8);
    crc_buf[5] = static_cast<uint8_t>(payload_len >> 16);
    crc_buf[6] = static_cast<uint8_t>(payload_len >> 24);
    if (payload_len > 0) memcpy(crc_buf + 7, payload, payload_len);
    uint16_t crc = Protocol::crc16(crc_buf, crc_len);

    // Assemble frame
    size_t i = 0;
    out[i++] = Protocol::FRAME_START_1;
    out[i++] = Protocol::FRAME_START_2;
    out[i++] = t;
    out[i++] = static_cast<uint8_t>(seq);
    out[i++] = static_cast<uint8_t>(seq >> 8);
    out[i++] = static_cast<uint8_t>(payload_len);
    out[i++] = static_cast<uint8_t>(payload_len >> 8);
    out[i++] = static_cast<uint8_t>(payload_len >> 16);
    out[i++] = static_cast<uint8_t>(payload_len >> 24);
    if (payload_len > 0) {
        memcpy(out + i, payload, payload_len);
        i += payload_len;
    }
    out[i++] = static_cast<uint8_t>(crc);
    out[i++] = static_cast<uint8_t>(crc >> 8);
    out[i++] = Protocol::FRAME_END_1;
    out[i++] = Protocol::FRAME_END_2;

    return i;
}

bool BluetoothComm::send(Protocol::MsgType type,
                          const uint8_t* payload, size_t payload_len)
{
    if (!isConnected()) return false;

    size_t buf_size = Protocol::OVERHEAD + payload_len;
    uint8_t* buf = static_cast<uint8_t*>(malloc(buf_size));
    if (!buf) return false;

    if (xSemaphoreTake(_tx_mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        free(buf);
        return false;
    }

    size_t frame_len = _buildFrame(type, payload, payload_len, buf, buf_size);
    if (frame_len > 0) {
        _bt.write(buf, frame_len);
        _tx_frame_count++;
    }

    xSemaphoreGive(_tx_mutex);
    free(buf);
    return (frame_len > 0);
}

bool BluetoothComm::sendImageChunk(const Protocol::ImageChunkHeader& header,
                                    const uint8_t* jpeg_data, size_t jpeg_len)
{
    // Compose: ImageChunkHeader + raw JPEG bytes
    size_t total = sizeof(header) + jpeg_len;
    uint8_t* payload = static_cast<uint8_t*>(malloc(total));
    if (!payload) return false;

    memcpy(payload, &header, sizeof(header));
    memcpy(payload + sizeof(header), jpeg_data, jpeg_len);

    bool ok = send(Protocol::MsgType::IMAGE_CHUNK, payload, total);
    free(payload);
    return ok;
}

bool BluetoothComm::sendAck(uint16_t acked_seq, uint8_t status) {
    Protocol::AckPayload ack { acked_seq, status };
    return send(Protocol::MsgType::ACK,
                reinterpret_cast<const uint8_t*>(&ack),
                sizeof(ack));
}

bool BluetoothComm::sendHeartbeat() {
    return send(Protocol::MsgType::HEARTBEAT, nullptr, 0);
}

// ---------------------------------------------------------------------------
// Callbacks & status
// ---------------------------------------------------------------------------
void BluetoothComm::onMessage(Protocol::MsgType type, MessageCallback cb) {
    _callbacks[static_cast<uint8_t>(type)] = cb;
}

bool BluetoothComm::isConnected() const {
    return _bt.connected();
}
