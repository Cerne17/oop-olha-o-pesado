#pragma once
// =============================================================================
// Protocol.h — Shared binary protocol between ESP32 and the host computer.
//
// Frame layout (all multi-byte fields are little-endian):
//
//   [0xCA][0xFE]              — start magic (2 bytes)
//   [MSG_TYPE]                — 1 byte  (MsgType enum)
//   [SEQ_NUM]                 — 2 bytes (uint16, rolls over at 65535)
//   [PAYLOAD_LEN]             — 4 bytes (uint32, bytes that follow)
//   [PAYLOAD ...]             — variable
//   [CRC16]                   — 2 bytes (CRC-16/CCITT over TYPE+SEQ+LEN+PAYLOAD)
//   [0xED][0xED]              — end magic (2 bytes)
//
// =============================================================================

#include <stdint.h>
#include <stddef.h>

// ---------------------------------------------------------------------------
// Frame constants
// ---------------------------------------------------------------------------
namespace Protocol {

constexpr uint8_t FRAME_START_1 = 0xCA;
constexpr uint8_t FRAME_START_2 = 0xFE;
constexpr uint8_t FRAME_END_1   = 0xED;
constexpr uint8_t FRAME_END_2   = 0xED;

constexpr size_t HEADER_SIZE    = 9;  // start(2) + type(1) + seq(2) + len(4)
constexpr size_t FOOTER_SIZE    = 4;  // crc(2) + end(2)
constexpr size_t OVERHEAD       = HEADER_SIZE + FOOTER_SIZE;

// Maximum bytes per image chunk (fits comfortably inside a BT SPP packet)
constexpr size_t IMAGE_CHUNK_DATA_SIZE = 512;

// ---------------------------------------------------------------------------
// Message types
// ---------------------------------------------------------------------------
enum class MsgType : uint8_t {
    IMAGE_CHUNK   = 0x01,  // ESP32 → PC  : one chunk of a JPEG frame
    TELEMETRY     = 0x02,  // ESP32 → PC  : wheel RPM + speed
    WHEEL_CONTROL = 0x03,  // PC → ESP32  : target power per wheel
    ACK           = 0x04,  // bidirectional acknowledgement
    HEARTBEAT     = 0x05,  // bidirectional keep-alive
};

// ---------------------------------------------------------------------------
// Payloads (packed — no padding bytes)
// ---------------------------------------------------------------------------

// Prefixed to every image chunk payload before the raw JPEG bytes
struct ImageChunkHeader {
    uint16_t frame_id;      // monotonically increasing frame identifier
    uint16_t chunk_idx;     // 0-based chunk index
    uint16_t total_chunks;  // total chunks in this frame
    uint32_t total_size;    // total JPEG size in bytes
} __attribute__((packed));

struct TelemetryPayload {
    float    left_rpm;      // left wheel RPM  (positive = forward)
    float    right_rpm;     // right wheel RPM (positive = forward)
    float    speed_mps;     // measured linear speed in m/s
    uint32_t timestamp_ms;  // millis() at the time of measurement
} __attribute__((packed));

struct WheelControlPayload {
    float left_power;   // [-1.0, 1.0]  (negative = reverse)
    float right_power;  // [-1.0, 1.0]
} __attribute__((packed));

struct AckPayload {
    uint16_t acked_seq;  // sequence number being acknowledged
    uint8_t  status;     // 0 = OK, 1 = CHECKSUM_ERROR, 2 = UNKNOWN_TYPE
} __attribute__((packed));

// ---------------------------------------------------------------------------
// CRC-16/CCITT (XModem variant) — polynomial 0x1021, init 0x0000
// Covers: msg_type(1) + seq_num(2) + payload_len(4) + payload(N)
// ---------------------------------------------------------------------------
inline uint16_t crc16(const uint8_t* data, size_t len) {
    uint16_t crc = 0x0000;
    for (size_t i = 0; i < len; i++) {
        crc ^= static_cast<uint16_t>(data[i]) << 8;
        for (int j = 0; j < 8; j++) {
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
        }
    }
    return crc;
}

} // namespace Protocol
