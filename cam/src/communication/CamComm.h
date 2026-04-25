#pragma once
// =============================================================================
// cam/src/communication/CamComm.h — ESP32-CAM streaming orchestrator.
//
// Spawns two FreeRTOS tasks:
//
//   _cameraTask (core 0, priority 3) — captures JPEG from the camera,
//                 splits it into 512-byte chunks, sends IMAGE_CHUNK frames.
//                 Pauses when _bt_connected is false.
//
//   _rxTask     (core 1, priority 4) — receives ACK + HEARTBEAT from the
//                 Computer. Manages _bt_connected flag via heartbeat watchdog.
// =============================================================================

#include <Arduino.h>
#include <BluetoothSerial.h>
#include "esp_camera.h"
#include "../types/Protocol.h"

class CamComm {
public:
    static constexpr uint32_t HEARTBEAT_TIMEOUT_MS = 5000;  // 5 s

    // target_fps : desired frame rate (actual rate depends on JPEG size + BT bandwidth)
    // bt_name    : Bluetooth device name advertised to the computer
    CamComm(float target_fps = 6.0f, const char* bt_name = "RobotCAM");

    // Initialise camera hardware, BluetoothSerial, and start FreeRTOS tasks.
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

    // RX state machine (same byte-by-byte decoder as RobotComm)
    void _resetRx();
    void _feedByte(uint8_t b);
    void _dispatchFrame();

    // Camera init (AI Thinker pin map)
    bool _initCamera();

    BluetoothSerial   _bt;
    const char*       _bt_name;
    float             _target_fps;
    SemaphoreHandle_t _tx_mutex;

    uint16_t         _tx_seq   { 0 };
    uint16_t         _frame_id { 0 };

    volatile bool    _bt_connected  { false };
    volatile uint32_t _last_hb_rx_ms { 0 };

    // RX decoder state
    enum class RxState : uint8_t {
        WAIT_START_1, WAIT_START_2,
        READ_HEADER, READ_PAYLOAD,
        READ_CRC_LO, READ_CRC_HI,
        WAIT_END_1,  WAIT_END_2,
    };

    struct RxCtx {
        RxState  state       { RxState::WAIT_START_1 };
        uint8_t  msg_type    { 0 };
        uint16_t seq_num     { 0 };
        uint32_t payload_len { 0 };
        uint16_t crc_rx      { 0 };
        size_t   bytes_read  { 0 };
    } _rx;

    static constexpr size_t MAX_PAYLOAD = 8;
    uint8_t _payload_buf[MAX_PAYLOAD];
};
