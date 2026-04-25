#pragma once
// =============================================================================
// robot/src/types/Protocol.h — Link B wire constants (Computer ↔ Robot).
//
// Frame layout (all multi-byte fields are little-endian):
//
//   [0xCA][0xFE]     start magic   (2 bytes)
//   [MSG_TYPE]       1 byte  (MsgType enum)
//   [SEQ_NUM]        2 bytes (uint16, rolls over at 65535)
//   [PAYLOAD_LEN]    4 bytes (uint32)
//   [PAYLOAD ...]    variable
//   [CRC16]          2 bytes (CRC-16/CCITT over TYPE+SEQ+LEN+PAYLOAD)
//   [0xED][0xED]     end magic     (2 bytes)
//
// Shared between robot/communication/ and robot/control/ without either
// module depending on the other. See SPEC.md §3 and §12.
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

// ---------------------------------------------------------------------------
// Message types — Link B
// ---------------------------------------------------------------------------
enum class MsgType : uint8_t {
    CONTROL_REF = 0x01,  // Computer → Robot : angle_deg + speed_ref
    ACK         = 0x02,  // Both             : acknowledgement
    HEARTBEAT   = 0x03,  // Both             : keep-alive (empty payload)
};

// ---------------------------------------------------------------------------
// Payloads (packed — no compiler padding)
// ---------------------------------------------------------------------------

// CONTROL_REF: reference signal sent by the computer.
//
//   angle_deg — direction clockwise from straight forward:
//                 0°    = straight forward
//                90°    = pivot right
//               -90°    = pivot left
//              ±180°    = straight backward
//
//   speed_ref — speed magnitude:
//               +1.0 = maximum forward speed
//                0.0 = stopped
//               -1.0 = maximum reverse speed
struct ControlRefPayload {
    float angle_deg;  // [-180.0, 180.0]
    float speed_ref;  // [-1.0, 1.0]
} __attribute__((packed));

// ACK
struct AckPayload {
    uint16_t acked_seq;  // sequence number being acknowledged
    uint8_t  status;     // 0=OK  1=CRC_ERROR  2=UNKNOWN_TYPE  3=INCOMPLETE
} __attribute__((packed));

// ---------------------------------------------------------------------------
// CRC-16/CCITT (XModem) — polynomial 0x1021, init 0x0000
// Covers: msg_type(1) + seq_num(2) + payload_len(4) + payload(N)
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
