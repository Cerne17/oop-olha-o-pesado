#include "CamComm.h"
#include "credentials.h"
#include <string.h>

// =============================================================================
// CamComm — implementation
// =============================================================================

// AI Thinker ESP32-CAM pin map
namespace {
constexpr int PWDN_GPIO  = 32;
constexpr int RESET_GPIO = -1;
constexpr int XCLK_GPIO  =  0;
constexpr int SIOD_GPIO  = 26;
constexpr int SIOC_GPIO  = 27;
constexpr int Y9_GPIO    = 35;
constexpr int Y8_GPIO    = 34;
constexpr int Y7_GPIO    = 39;
constexpr int Y6_GPIO    = 36;
constexpr int Y5_GPIO    = 21;
constexpr int Y4_GPIO    = 19;
constexpr int Y3_GPIO    = 18;
constexpr int Y2_GPIO    =  5;
constexpr int VSYNC_GPIO = 25;
constexpr int HREF_GPIO  = 23;
constexpr int PCLK_GPIO  = 22;
} // namespace

CamComm::CamComm(float target_fps, uint16_t listen_port)
    : _listen_port(listen_port), _target_fps(target_fps)
{
    _tx_mutex = xSemaphoreCreateMutex();
}

void CamComm::begin() {
    if (!_initCamera()) {
        Serial.println("[CAM] FATAL: camera init failed — halting");
        while (true) vTaskDelay(pdMS_TO_TICKS(1000));
    }

    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("[CAM] Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\n[CAM] WiFi IP: %s\n", WiFi.localIP().toString().c_str());

    _udp.begin(_listen_port);
    Serial.printf("[CAM] UDP listening on port %u\n", _listen_port);

    xTaskCreatePinnedToCore(_cameraTask, "cam", 8192, this, 3, nullptr, 0);
    xTaskCreatePinnedToCore(_rxTask,     "rx",  4096, this, 4, nullptr, 1);
}

// ---------------------------------------------------------------------------
// Camera task — capture + chunk + send
// ---------------------------------------------------------------------------

void CamComm::_cameraTask(void* arg) {
    auto* self = static_cast<CamComm*>(arg);
    const uint32_t interval_ms = (uint32_t)(1000.0f / self->_target_fps);

    for (;;) {
        if (!self->_client_known) {
            // No heartbeat received yet — destination unknown, can't send frames.
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        camera_fb_t* fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("[CAM] Frame capture failed");
            vTaskDelay(pdMS_TO_TICKS(interval_ms));
            continue;
        }

        uint32_t total_size   = fb->len;
        uint16_t total_chunks = (uint16_t)((total_size + Protocol::IMAGE_CHUNK_DATA_SIZE - 1)
                                            / Protocol::IMAGE_CHUNK_DATA_SIZE);

        for (uint16_t i = 0; i < total_chunks; ++i) {
            if (!self->_client_known) break;

            size_t offset    = i * Protocol::IMAGE_CHUNK_DATA_SIZE;
            size_t chunk_len = total_size - offset;
            if (chunk_len > Protocol::IMAGE_CHUNK_DATA_SIZE)
                chunk_len = Protocol::IMAGE_CHUNK_DATA_SIZE;

            self->_sendChunk(self->_tx_seq++, self->_frame_id,
                             i, total_chunks, total_size,
                             fb->buf + offset, chunk_len);
            vTaskDelay(0);  // yield between chunks
        }

        esp_camera_fb_return(fb);
        self->_frame_id = (self->_frame_id + 1) & 0xFFFF;

        vTaskDelay(pdMS_TO_TICKS(interval_ms));
    }
}

// ---------------------------------------------------------------------------
// RX task — ACK + HEARTBEAT receive
// ---------------------------------------------------------------------------

void CamComm::_rxTask(void* arg) {
    auto* self = static_cast<CamComm*>(arg);
    uint8_t buf[256];

    for (;;) {
        int pkt_size = self->_udp.parsePacket();
        if (pkt_size > 0) {
            // Record sender address so IMAGE_CHUNK frames go to the right host/port.
            self->_client_ip   = self->_udp.remoteIP();
            self->_client_port = self->_udp.remotePort();

            int n = self->_udp.read(buf, sizeof(buf));
            for (int i = 0; i < n; i++) {
                self->_feedByte(buf[i]);
            }
        }

        // Heartbeat watchdog — pause streaming if computer goes silent.
        if (self->_last_hb_rx_ms > 0 &&
            millis() - self->_last_hb_rx_ms > HEARTBEAT_TIMEOUT_MS)
        {
            if (self->_client_known) {
                Serial.println("[CAM] Heartbeat timeout — pausing stream");
                self->_client_known = false;
            }
        }

        vTaskDelay(pdMS_TO_TICKS(2));
    }
}

// ---------------------------------------------------------------------------
// Frame building
// ---------------------------------------------------------------------------

void CamComm::_sendChunk(uint16_t seq, uint16_t frame_id,
                          uint16_t chunk_idx, uint16_t total_chunks,
                          uint32_t total_size,
                          const uint8_t* data, size_t data_len) {
    Protocol::ImageChunkHeader hdr {
        frame_id, chunk_idx, total_chunks, total_size
    };

    size_t payload_len = sizeof(hdr) + data_len;
    size_t frame_len   = Protocol::OVERHEAD + payload_len;

    uint8_t* buf = new uint8_t[frame_len];
    if (!buf) return;

    uint8_t* p = buf;

    *p++ = Protocol::FRAME_START_1;
    *p++ = Protocol::FRAME_START_2;

    // Header: type(1) + seq(2 LE) + payload_len(4 LE)
    uint8_t* crc_start = p;
    *p++ = static_cast<uint8_t>(Protocol::MsgType::IMAGE_CHUNK);
    *p++ = (uint8_t)(seq);           // seq low byte
    *p++ = (uint8_t)(seq >> 8);      // seq high byte
    *p++ = (uint8_t)(payload_len);
    *p++ = (uint8_t)(payload_len >> 8);
    *p++ = (uint8_t)(payload_len >> 16);
    *p++ = (uint8_t)(payload_len >> 24);

    memcpy(p, &hdr,  sizeof(hdr));  p += sizeof(hdr);
    memcpy(p, data,  data_len);     p += data_len;

    uint16_t crc = Protocol::crc16(crc_start, 7 + payload_len);
    *p++ = (uint8_t)(crc);
    *p++ = (uint8_t)(crc >> 8);
    *p++ = Protocol::FRAME_END_1;
    *p++ = Protocol::FRAME_END_2;

    _udpSend(buf, frame_len);
    delete[] buf;
}

void CamComm::_sendHeartbeat(uint16_t seq) {
    uint8_t buf[Protocol::OVERHEAD];
    uint8_t* p = buf;

    *p++ = Protocol::FRAME_START_1;
    *p++ = Protocol::FRAME_START_2;

    uint8_t* crc_start = p;
    *p++ = static_cast<uint8_t>(Protocol::MsgType::HEARTBEAT);
    *p++ = (uint8_t)(seq);       // seq low byte
    *p++ = (uint8_t)(seq >> 8);  // seq high byte
    *p++ = 0; *p++ = 0; *p++ = 0; *p++ = 0;  // payload_len = 0

    uint16_t crc = Protocol::crc16(crc_start, 7);
    *p++ = (uint8_t)(crc);
    *p++ = (uint8_t)(crc >> 8);
    *p++ = Protocol::FRAME_END_1;
    *p++ = Protocol::FRAME_END_2;

    _udpSend(buf, Protocol::OVERHEAD);
}

void CamComm::_udpSend(const uint8_t* data, size_t len) {
    // No destination known yet — first heartbeat from the computer sets _client_port.
    if (_client_port == 0) return;
    xSemaphoreTake(_tx_mutex, portMAX_DELAY);
    _udp.beginPacket(_client_ip, _client_port);
    _udp.write(data, len);
    _udp.endPacket();
    xSemaphoreGive(_tx_mutex);
}

// ---------------------------------------------------------------------------
// RX state machine
// ---------------------------------------------------------------------------

void CamComm::_resetRx() {
    _rx.state       = RxState::WAIT_START_1;
    _rx.bytes_read  = 0;
    _rx.payload_len = 0;
}

void CamComm::_feedByte(uint8_t b) {
    switch (_rx.state) {

    case RxState::WAIT_START_1:
        if (b == Protocol::FRAME_START_1) _rx.state = RxState::WAIT_START_2;
        break;

    case RxState::WAIT_START_2:
        _rx.bytes_read = 0;
        if (b == Protocol::FRAME_START_2) {
            _rx.state = RxState::READ_HEADER;
        } else if (b == Protocol::FRAME_START_1) {
            // Another 0xCA before 0xFE — re-arm rather than discard.
            // Dropping it would lose the next frame's opening byte.
            _rx.state = RxState::WAIT_START_2;
        } else {
            _rx.state = RxState::WAIT_START_1;
        }
        break;

    case RxState::READ_HEADER: {
        // Accumulate into hdr_buf, then unpack explicitly (avoids struct overlay UB).
        // Wire layout (little-endian): [msg_type:1][seq:2][payload_len:4]
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
            // Unexpected byte — discard frame. Re-arm if byte is a frame start
            // so the next 0xFE is not lost.
            _resetRx();
            if (b == Protocol::FRAME_START_1) _rx.state = RxState::WAIT_START_2;
        }
        break;

    case RxState::WAIT_END_2:
        if (b == Protocol::FRAME_END_2) _dispatchFrame();
        _resetRx();
        break;
    }
}

void CamComm::_dispatchFrame() {
    // Re-serialize parsed header fields for CRC verification.
    uint8_t crc_input[7 + MAX_PAYLOAD];
    crc_input[0] = _rx.msg_type;
    crc_input[1] = (uint8_t)(_rx.seq_num);
    crc_input[2] = (uint8_t)(_rx.seq_num >> 8);
    crc_input[3] = (uint8_t)(_rx.payload_len);
    crc_input[4] = (uint8_t)(_rx.payload_len >> 8);
    crc_input[5] = (uint8_t)(_rx.payload_len >> 16);
    crc_input[6] = (uint8_t)(_rx.payload_len >> 24);
    memcpy(crc_input + 7, _payload_buf, _rx.payload_len);

    uint16_t computed = Protocol::crc16(crc_input, 7 + _rx.payload_len);
    if (computed != _rx.crc_rx) return;  // drop silently — CAM doesn't send NACKs

    switch (static_cast<Protocol::MsgType>(_rx.msg_type)) {

    case Protocol::MsgType::ACK:
        if (_rx.payload_len == sizeof(Protocol::AckPayload)) {
            Protocol::AckPayload ack;
            memcpy(&ack, _payload_buf, sizeof(ack));
            if (ack.status != 0)
                Serial.printf("[CAM] NACK seq=%u status=%u\n",
                              ack.acked_seq, (uint8_t)ack.status);
        }
        break;

    case Protocol::MsgType::HEARTBEAT:
        _client_known   = true;
        _last_hb_rx_ms  = millis();
        _sendHeartbeat(_tx_seq++);
        break;

    default:
        break;
    }
}

// ---------------------------------------------------------------------------
// Camera hardware init (AI Thinker pin map)
// ---------------------------------------------------------------------------

bool CamComm::_initCamera() {
    camera_config_t config = {};

    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer   = LEDC_TIMER_0;
    config.pin_d0       = Y2_GPIO;
    config.pin_d1       = Y3_GPIO;
    config.pin_d2       = Y4_GPIO;
    config.pin_d3       = Y5_GPIO;
    config.pin_d4       = Y6_GPIO;
    config.pin_d5       = Y7_GPIO;
    config.pin_d6       = Y8_GPIO;
    config.pin_d7       = Y9_GPIO;
    config.pin_xclk     = XCLK_GPIO;
    config.pin_pclk     = PCLK_GPIO;
    config.pin_vsync    = VSYNC_GPIO;
    config.pin_href     = HREF_GPIO;
    config.pin_sccb_sda = SIOD_GPIO;
    config.pin_sccb_scl = SIOC_GPIO;
    config.pin_pwdn     = PWDN_GPIO;
    config.pin_reset    = RESET_GPIO;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size   = FRAMESIZE_QVGA;   // 320×240
    config.jpeg_quality = 15;
    config.fb_count     = 1;

    return esp_camera_init(&config) == ESP_OK;
}
