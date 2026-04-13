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
// Data flow:
//   ESP32 → PC : IMAGE_CHUNK  (live camera stream)
//   PC → ESP32 : DIRECTION_REF (angle + stop flag; robot drives its own wheels)
//   Both       : ACK, HEARTBEAT
// =============================================================================

#include <stdint.h>
#include <stddef.h>

namespace Protocol {

// ---------------------------------------------------------------------------
// Frame constants
// ---------------------------------------------------------------------------
constexpr uint8_t FRAME_START_1 = 0xCA;
constexpr uint8_t FRAME_START_2 = 0xFE;
constexpr uint8_t FRAME_END_1   = 0xED;
constexpr uint8_t FRAME_END_2   = 0xED;

constexpr size_t HEADER_SIZE = 9;   // start(2) + type(1) + seq(2) + len(4)
constexpr size_t FOOTER_SIZE = 4;   // crc(2) + end(2)
constexpr size_t OVERHEAD    = HEADER_SIZE + FOOTER_SIZE;

// Maximum JPEG bytes per image chunk
constexpr size_t IMAGE_CHUNK_DATA_SIZE = 512;

// ---------------------------------------------------------------------------
// Message types
// ---------------------------------------------------------------------------
enum class MsgType : uint8_t {
    IMAGE_CHUNK   = 0x01,  // ESP32 → PC   : one 512-byte chunk of a JPEG frame
    DIRECTION_REF = 0x02,  // PC → ESP32   : reference angle + stop flag
    ACK           = 0x03,  // bidirectional : acknowledgement
    HEARTBEAT     = 0x04,  // bidirectional : keep-alive (empty payload)
};

// ---------------------------------------------------------------------------
// Payloads (packed — no compiler-inserted padding)
// ---------------------------------------------------------------------------

// IMAGE_CHUNK: prefixed to every chunk before the raw JPEG bytes
struct ImageChunkHeader {
    uint16_t frame_id;      // monotonically increasing frame identifier
    uint16_t chunk_idx;     // 0-based chunk index within this frame
    uint16_t total_chunks;  // total chunks that make up this frame
    uint32_t total_size;    // total JPEG byte count for this frame
} __attribute__((packed));

// DIRECTION_REF: the reference signal sent by the computer.
//
//   angle_deg — direction the robot should move, measured clockwise from
//               straight forward:
//                  0°        = straight forward
//                 90°        = turn right (pivot)
//                -90°        = turn left  (pivot)
//               ±180°        = straight backward
//
//   stop      — when non-zero the robot must come to a smooth stop regardless
//               of angle_deg.
struct DirectionRefPayload {
    float   angle_deg;  // [-180.0, 180.0]
    uint8_t stop;       // 0 = move, 1 = stop
} __attribute__((packed));

// ACK
struct AckPayload {
    uint16_t acked_seq;  // sequence number being acknowledged
    uint8_t  status;     // 0 = OK, 1 = CRC_ERROR, 2 = UNKNOWN_TYPE
} __attribute__((packed));

// ---------------------------------------------------------------------------
// CRC-16/CCITT (XModem) — polynomial 0x1021, init 0x0000
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
