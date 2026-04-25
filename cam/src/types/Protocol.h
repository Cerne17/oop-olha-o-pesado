#pragma once
// =============================================================================
// cam/src/types/Protocol.h — Link A wire constants (Computer ↔ CAM).
//
// Frame layout identical to robot/src/types/Protocol.h.
// Message type values are independent (Link A namespace).
//
// Keep this file in sync with robot/src/types/Protocol.h whenever the shared
// wire framing (magic bytes, CRC, header layout) changes. Do NOT share a
// single header between the two PlatformIO projects — they have independent
// build graphs. See SPEC.md §11.1.
// =============================================================================

#include <stdint.h>
#include <stddef.h>

namespace Protocol {

// ---------------------------------------------------------------------------
// Frame constants (identical to robot/src/types/Protocol.h)
// ---------------------------------------------------------------------------
constexpr uint8_t FRAME_START_1 = 0xCA;
constexpr uint8_t FRAME_START_2 = 0xFE;
constexpr uint8_t FRAME_END_1   = 0xED;
constexpr uint8_t FRAME_END_2   = 0xED;

constexpr size_t HEADER_SIZE = 9;
constexpr size_t FOOTER_SIZE = 4;
constexpr size_t OVERHEAD    = HEADER_SIZE + FOOTER_SIZE;

constexpr size_t IMAGE_CHUNK_DATA_SIZE = 512;  // max JPEG bytes per chunk

// ---------------------------------------------------------------------------
// Message types — Link A
// ---------------------------------------------------------------------------
enum class MsgType : uint8_t {
    IMAGE_CHUNK = 0x01,  // CAM → Computer : one chunk of a JPEG frame
    ACK         = 0x02,  // Computer → CAM : acknowledgement
    HEARTBEAT   = 0x03,  // Both           : keep-alive (empty payload)
};

// ---------------------------------------------------------------------------
// Payloads (packed)
// ---------------------------------------------------------------------------

// IMAGE_CHUNK: header prefixed to each chunk before the raw JPEG bytes.
struct ImageChunkHeader {
    uint16_t frame_id;      // monotonically increasing, wraps at 65535
    uint16_t chunk_idx;     // 0-based index within this frame
    uint16_t total_chunks;  // total chunks for this frame
    uint32_t total_size;    // total JPEG byte count for this frame
} __attribute__((packed));

// ACK
struct AckPayload {
    uint16_t acked_seq;  // SEQ_NUM being acknowledged
    uint8_t  status;     // 0=OK  1=CRC_ERROR  2=UNKNOWN_TYPE  3=INCOMPLETE
} __attribute__((packed));

// ---------------------------------------------------------------------------
// CRC-16/CCITT (XModem) — identical to robot version
// ---------------------------------------------------------------------------
inline uint16_t crc16(const uint8_t* data, size_t len) {
    uint16_t crc = 0x0000;
    for (size_t i = 0; i < len; ++i) {
        crc ^= static_cast<uint16_t>(data[i]) << 8;
        for (int j = 0; j < 8; ++j)
            crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
    return crc;
}

} // namespace Protocol
