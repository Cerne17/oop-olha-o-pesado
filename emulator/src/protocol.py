"""
emulator.protocol -- binary protocol for Link B (Computer <-> Robot).

Self-contained: no imports from computer/. Wire format is identical to
computer/communication/protocol.py (RobotMsg namespace).

Spec reference: emulator/SPEC.md §3.
"""

from __future__ import annotations

import struct
from typing import Generator

# ---------------------------------------------------------------------------
# Frame constants
# ---------------------------------------------------------------------------

START_BYTE_1 = 0xCA
START_BYTE_2 = 0xFE
END_BYTE_1   = 0xED
END_BYTE_2   = 0xED

# Minimum frame size: 2 start + 1 type + 2 seq + 4 len + 2 crc + 2 end = 13
MIN_FRAME_SIZE = 13

# ---------------------------------------------------------------------------
# Message types -- Link B (Robot link)
# ---------------------------------------------------------------------------

MSG_CONTROL_REF = 0x01   # Computer -> Robot : angle_deg + speed_ref
MSG_ACK         = 0x02   # Robot -> Computer : acknowledgement
MSG_HEARTBEAT   = 0x03   # Both              : keep-alive, empty payload

# ---------------------------------------------------------------------------
# CRC-16/CCITT (XModem)
# ---------------------------------------------------------------------------

def crc16(data: bytes) -> int:
    """CRC-16/CCITT XModem: poly=0x1021, init=0x0000, no reflection."""
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
        crc &= 0xFFFF
    return crc


# ---------------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------------

class FrameEncoder:
    """Builds binary frames from message components."""

    def build(self, msg_type: int, seq: int, payload: bytes) -> bytes:
        crc_input = struct.pack('<BHI', msg_type, seq, len(payload)) + payload
        crc = crc16(crc_input)
        return (
            bytes([START_BYTE_1, START_BYTE_2])
            + struct.pack('<BHI', msg_type, seq, len(payload))
            + payload
            + struct.pack('<H', crc)
            + bytes([END_BYTE_1, END_BYTE_2])
        )

    def build_ack(self, seq: int, acked_seq: int, status: int) -> bytes:
        payload = struct.pack('<HB', acked_seq, status)
        return self.build(MSG_ACK, seq, payload)

    def build_heartbeat(self, seq: int) -> bytes:
        return self.build(MSG_HEARTBEAT, seq, b'')


# ---------------------------------------------------------------------------
# Decoded frame
# ---------------------------------------------------------------------------

class DecodedFrame:
    """Holds a fully parsed incoming frame."""

    __slots__ = ('msg_type', 'seq_num', 'payload', 'crc_ok')

    def __init__(self,
                 msg_type: int,
                 seq_num:  int,
                 payload:  bytes,
                 crc_ok:   bool) -> None:
        self.msg_type = msg_type
        self.seq_num  = seq_num
        self.payload  = payload
        self.crc_ok   = crc_ok

    def decode_control_ref(self) -> tuple[float, float]:
        """Returns (angle_deg, speed_ref). Payload must be 8 bytes."""
        angle_deg, speed_ref = struct.unpack('<ff', self.payload[:8])
        return angle_deg, speed_ref

    def decode_ack(self) -> tuple[int, int]:
        """Returns (acked_seq, status)."""
        acked_seq, status = struct.unpack('<HB', self.payload[:3])
        return acked_seq, status


# ---------------------------------------------------------------------------
# Streaming decoder
# ---------------------------------------------------------------------------

class FrameDecoder:
    """Feed raw bytes; yields DecodedFrame objects as they become complete."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> Generator[DecodedFrame, None, None]:
        self._buf.extend(data)
        while True:
            frame = self._try_decode()
            if frame is None:
                break
            yield frame

    def _try_decode(self) -> DecodedFrame | None:
        buf = self._buf

        # Scan for start bytes
        while len(buf) >= 2:
            if buf[0] == START_BYTE_1 and buf[1] == START_BYTE_2:
                break
            buf.pop(0)

        if len(buf) < 9:
            return None

        msg_type, seq_num, payload_len = struct.unpack_from('<BHI', buf, 2)
        total_len = MIN_FRAME_SIZE + payload_len

        if len(buf) < total_len:
            return None

        if buf[total_len - 2] != END_BYTE_1 or buf[total_len - 1] != END_BYTE_2:
            del buf[0]
            return None

        payload    = bytes(buf[9: 9 + payload_len])
        crc_stored, = struct.unpack_from('<H', buf, 9 + payload_len)

        crc_input = struct.pack('<BHI', msg_type, seq_num, payload_len) + payload
        crc_ok    = crc16(crc_input) == crc_stored

        del buf[:total_len]
        return DecodedFrame(msg_type, seq_num, payload, crc_ok)
