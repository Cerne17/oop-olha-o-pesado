#pragma once
// =============================================================================
// BluetoothComm.h — Bluetooth Classic SPP transport layer for the ESP32.
//
// Wraps BluetoothSerial with:
//   - Frame encoding / decoding using Protocol.h
//   - Non-blocking receive state-machine (call poll() from the main loop)
//   - Thread-safe send() usable from any FreeRTOS task
//   - Callback registration per MsgType
// =============================================================================

#include <Arduino.h>
#include <BluetoothSerial.h>
#include <functional>
#include <map>
#include "Protocol.h"

// Callback signature: (payload_ptr, payload_len)
using MessageCallback = std::function<void(const uint8_t*, size_t)>;

class BluetoothComm {
public:
    // -------------------------------------------------------------------------
    // Construction
    // -------------------------------------------------------------------------
    explicit BluetoothComm(const char* device_name);

    // -------------------------------------------------------------------------
    // Lifecycle
    // -------------------------------------------------------------------------

    // Initialise the BluetoothSerial stack and start advertising.
    // Returns false if the underlying stack fails to start.
    bool begin();

    // Must be called repeatedly from the main loop (or a dedicated FreeRTOS
    // task). Reads available bytes and drives the receive state-machine.
    void poll();

    // Shut down the Bluetooth stack gracefully.
    void end();

    // -------------------------------------------------------------------------
    // Sending
    // -------------------------------------------------------------------------

    // Encode and transmit a message. Thread-safe (uses a mutex internally).
    // Returns false if not connected or if serialisation fails.
    bool send(Protocol::MsgType type, const uint8_t* payload, size_t payload_len);

    // Convenience overloads for known payload structs
    bool sendImageChunk(const Protocol::ImageChunkHeader& header,
                        const uint8_t* jpeg_data, size_t jpeg_len);
    bool sendAck(uint16_t acked_seq, uint8_t status = 0);
    bool sendHeartbeat();

    // -------------------------------------------------------------------------
    // Receiving — callback registration
    // -------------------------------------------------------------------------

    // Register a callback for a specific message type. Replaces any existing
    // callback for that type. Called from the poll() context (same task).
    void onMessage(Protocol::MsgType type, MessageCallback cb);

    // -------------------------------------------------------------------------
    // Status
    // -------------------------------------------------------------------------
    bool isConnected() const;
    uint32_t rxFrameCount()  const { return _rx_frame_count; }
    uint32_t rxErrorCount()  const { return _rx_error_count; }
    uint32_t txFrameCount()  const { return _tx_frame_count; }

private:
    // -------------------------------------------------------------------------
    // Receive state machine
    // -------------------------------------------------------------------------
    enum class RxState {
        WAIT_START_1,
        WAIT_START_2,
        READ_HEADER,   // reads type(1)+seq(2)+len(4) — 7 bytes
        READ_PAYLOAD,
        READ_CRC_1,
        READ_CRC_2,
        WAIT_END_1,
        WAIT_END_2,
    };

    void _processReceivedByte(uint8_t byte);
    void _dispatchFrame();
    void _resetRx();

    // -------------------------------------------------------------------------
    // Frame building helper
    // -------------------------------------------------------------------------
    size_t _buildFrame(Protocol::MsgType type,
                       const uint8_t* payload, size_t payload_len,
                       uint8_t* out_buf, size_t out_buf_size);

    // -------------------------------------------------------------------------
    // Members
    // -------------------------------------------------------------------------
    BluetoothSerial       _bt;
    const char*           _device_name;
    SemaphoreHandle_t     _tx_mutex;
    uint16_t              _tx_seq { 0 };

    // RX state machine
    RxState  _rx_state  { RxState::WAIT_START_1 };
    uint8_t  _rx_type   { 0 };
    uint16_t _rx_seq    { 0 };
    uint32_t _rx_len    { 0 };
    uint16_t _rx_crc    { 0 };
    size_t   _rx_bytes_read { 0 };

    // We allocate the payload buffer dynamically per frame to handle large images.
    uint8_t* _rx_payload_buf { nullptr };

    // Callbacks
    std::map<uint8_t, MessageCallback> _callbacks;

    // Stats
    uint32_t _rx_frame_count { 0 };
    uint32_t _rx_error_count { 0 };
    uint32_t _tx_frame_count { 0 };

    static constexpr size_t TX_BUF_SIZE = Protocol::IMAGE_CHUNK_DATA_SIZE
                                        + sizeof(Protocol::ImageChunkHeader)
                                        + Protocol::OVERHEAD;

    // Note: the ESP32 does not send DIRECTION_REF — it only receives it.
    // Register a handler via onMessage(MsgType::DIRECTION_REF, cb).
};
