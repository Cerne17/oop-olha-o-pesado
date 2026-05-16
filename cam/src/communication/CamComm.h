#pragma once
// =============================================================================
// cam/src/communication/CamComm.h — ESP32-CAM streaming orchestrator.
//
// Spawns two FreeRTOS tasks:
//
//   _cameraTask (core 0, priority 3) — captures JPEG from the camera,
//                 splits it into 512-byte chunks, sends IMAGE_CHUNK frames
//                 via UDP. Pauses until the first heartbeat is received from
//                 the computer (which reveals the destination IP:port).
//
//   _rxTask     (core 1, priority 4) — receives ACK + HEARTBEAT datagrams
//                 from the computer. Records the sender address on first
//                 heartbeat; manages _client_known flag via timeout watchdog.
// =============================================================================

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include "esp_camera.h"
#include "../types/Protocol.h"

class CamComm {
public:
    static constexpr uint32_t HEARTBEAT_TIMEOUT_MS = 5000;  // 5 s

    // target_fps  : desired frame rate (actual rate depends on JPEG size + WiFi bandwidth)
    // listen_port : UDP port the CAM listens on for ACK/HEARTBEAT from computer
    CamComm(float target_fps = 6.0f, uint16_t listen_port = 5006);

    // Connect to WiFi, initialise camera hardware, and start FreeRTOS tasks.
    void begin();

private:
    static void _cameraTask(void* arg);   // core 0, priority 3, stack 8192 B
    static void _rxTask(void* arg);       // core 1, priority 4, stack 4096 B

    // Frame building / sending
    void _sendChunk(uint16_t seq, uint16_t frame_id,
                    uint16_t chunk_idx, uint16_t total_chunks,
                    uint32_t total_size,
                    const uint8_t* data, size_t data_len);
    void _sendHeartbeat(uint16_t seq);
    void _udpSend(const uint8_t* data, size_t len);

    // RX state machine (same byte-by-byte decoder as RobotComm)
    void _resetRx();
    void _feedByte(uint8_t b);
    void _dispatchFrame();

    // Camera init (AI Thinker pin map)
    bool _initCamera();

    WiFiUDP           _udp;
    uint16_t          _listen_port;
    // Set on first received datagram; all IMAGE_CHUNK frames go here.
    IPAddress         _client_ip;
    uint16_t          _client_port { 0 };

    float             _target_fps;
    SemaphoreHandle_t _tx_mutex;

    uint16_t          _tx_seq   { 0 };
    uint16_t          _frame_id { 0 };

    // True once the first heartbeat from the computer is received.
    // _cameraTask pauses while false — we don't know where to send frames yet.
    volatile bool     _client_known  { false };
    volatile uint32_t _last_hb_rx_ms { 0 };

    // Frame decoder state machine — advances byte-by-byte through:
    //   [START_1][START_2][header x7][payload x N][CRC_LO][CRC_HI][END_1][END_2]
    enum class RxState : uint8_t {
        WAIT_START_1,  // waiting for 0xCA
        WAIT_START_2,  // got 0xCA, waiting for 0xFE
        READ_HEADER,   // accumulating 7 header bytes (type + seq LE + len LE)
        READ_PAYLOAD,  // accumulating payload_len bytes
        READ_CRC_LO,   // low byte of received CRC16
        READ_CRC_HI,   // high byte of received CRC16
        WAIT_END_1,    // waiting for 0xED
        WAIT_END_2,    // waiting for second 0xED — dispatches on match
    };

    struct RxCtx {
        RxState  state       { RxState::WAIT_START_1 };
        uint8_t  msg_type    { 0 };
        uint16_t seq_num     { 0 };
        uint32_t payload_len { 0 };
        uint16_t crc_rx      { 0 };
        size_t   bytes_read  { 0 };
        // Staging buffer for the 7-byte wire header (type + seq LE + len LE).
        // Filled byte-by-byte in READ_HEADER, then unpacked explicitly.
        uint8_t  hdr_buf[7]  {};
    } _rx;

    static constexpr size_t MAX_PAYLOAD = 8;  // ACK=3, HB=0 (IMAGE_CHUNK sent, not received)
    uint8_t _payload_buf[MAX_PAYLOAD];
};
