#pragma once
// =============================================================================
// robot/src/communication/RobotComm.h — FreeRTOS task orchestrator.
//
// Spawns three tasks:
//
//   _udpTask     (core 1, priority 5) — UDP receive loop:
//                  decodes frames, dispatches CONTROL_REF to WheelController,
//                  sends ACK/HEARTBEAT, resets watchdog timer.
//
//   _controlTask (core 1, priority 4) — calls WheelController::update()
//                  at WheelController::CONTROL_HZ (50 Hz).
//
//   _watchdogTask (core 1, priority 3) — calls WheelController::emergencyStop()
//                  if no valid frame received within WATCHDOG_TIMEOUT_MS.
// =============================================================================

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include "../control/WheelController.h"
#include "../types/Protocol.h"

class RobotComm {
public:
    static constexpr uint32_t WATCHDOG_TIMEOUT_MS = 5000;  // 5 s

    RobotComm(WheelController& wheel, uint16_t listen_port = 5005);

    // Connect to WiFi and start FreeRTOS tasks.
    void begin();

private:
    static void _udpTask(void* arg);        // core 1, priority 5, stack 4096 B
    static void _controlTask(void* arg);    // core 1, priority 4, stack 2048 B
    static void _watchdogTask(void* arg);   // core 1, priority 3, stack 2048 B

    // Frame-building and send helpers
    size_t  _buildFrame(Protocol::MsgType type,
                        const uint8_t* payload, size_t payload_len,
                        uint8_t* out, size_t out_size);
    void    _sendAck(uint16_t acked_seq, uint8_t status);
    void    _sendHeartbeat();
    void    _udpSend(const uint8_t* data, size_t len);

    WheelController&  _wheel;
    WiFiUDP           _udp;
    uint16_t          _listen_port;
    // Set on first received datagram; used for all ACK/HEARTBEAT replies.
    IPAddress         _client_ip;
    uint16_t          _client_port { 0 };
    SemaphoreHandle_t _tx_mutex;
    uint16_t          _tx_seq { 0 };

    // Watchdog timestamp (set by _btTask, read by _watchdogTask)
    volatile uint32_t _last_rx_ms { 0 };

    // Frame decoder state machine
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
        // Staging buffer for the 7-byte wire header (type + seq LE + len LE).
        // Filled byte-by-byte in READ_HEADER, then unpacked explicitly.
        uint8_t  hdr_buf[7]  {};
    } _rx;

    void _resetRx();
    void _feedByte(uint8_t b);
    void _dispatchFrame();

    static constexpr size_t MAX_PAYLOAD = 16;  // CONTROL_REF=8, ACK=3, HB=0
    uint8_t _payload_buf[MAX_PAYLOAD];
};
