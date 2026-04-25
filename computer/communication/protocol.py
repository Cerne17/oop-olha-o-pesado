"""
computer.communication.protocol — binary frame encoder and decoder.

Self-contained: no I/O, no threading, no dependencies on other project modules.
Wire format defined in SPEC.md §3.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import ClassVar, Generator


# ---------------------------------------------------------------------------
# Frame constants
# ---------------------------------------------------------------------------
_START_1 = 0xCA
_START_2 = 0xFE
_END_1   = 0xED
_END_2   = 0xED

# Minimum frame size: 2 start + 1 type + 2 seq + 4 len + 2 crc + 2 end = 13
_MIN_FRAME = 13


# ---------------------------------------------------------------------------
# Message type namespaces
# ---------------------------------------------------------------------------

class CamMsg:
    """Message types on Link A (Computer ↔ CAM)."""
    IMAGE_CHUNK = 0x01
    ACK         = 0x02
    HEARTBEAT   = 0x03

class RobotMsg:
    """Message types on Link B (Computer ↔ Robot)."""
    CONTROL_REF = 0x01
    ACK         = 0x02
    HEARTBEAT   = 0x03

IMAGE_CHUNK_SIZE = 512  # max JPEG bytes per chunk


# ---------------------------------------------------------------------------
# CRC-16/CCITT (XModem)
# ---------------------------------------------------------------------------

def crc16(data: bytes) -> int:
    """CRC-16/CCITT XModem: poly=0x1021, init=0x0000, no reflection.
    Covers: MSG_TYPE(1) + SEQ_NUM(2) + PAYLOAD_LEN(4) + PAYLOAD(N).
    """
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
        crc &= 0xFFFF
    return crc


# ---------------------------------------------------------------------------
# Payload dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ImageChunkHeader:
    frame_id:     int  # uint16
    chunk_idx:    int  # uint16
    total_chunks: int  # uint16
    total_size:   int  # uint32

    SIZE: ClassVar[int] = 10
    _FMT: ClassVar[str] = '<HHHI'

    @classmethod
    def unpack(cls, data: bytes) -> ImageChunkHeader:
        fid, cidx, total, sz = struct.unpack_from(cls._FMT, data)
        return cls(fid, cidx, total, sz)

    def pack(self) -> bytes:
        return struct.pack(self._FMT,
                           self.frame_id, self.chunk_idx,
                           self.total_chunks, self.total_size)


@dataclass
class ControlRefPayload:
    angle_deg: float  # float32, [-180.0, 180.0]
    speed_ref: float  # float32, [-1.0, 1.0]

    _FMT: ClassVar[str] = '<ff'

    def pack(self) -> bytes:
        return struct.pack(self._FMT, self.angle_deg, self.speed_ref)

    @classmethod
    def unpack(cls, data: bytes) -> ControlRefPayload:
        angle, speed = struct.unpack_from(cls._FMT, data)
        return cls(angle, speed)


@dataclass
class AckPayload:
    acked_seq: int  # uint16
    status:    int  # uint8: 0=OK 1=CRC_ERROR 2=UNKNOWN_TYPE 3=INCOMPLETE

    SIZE: ClassVar[int] = 3
    _FMT: ClassVar[str] = '<HB'

    def pack(self) -> bytes:
        return struct.pack(self._FMT, self.acked_seq, self.status)

    @classmethod
    def unpack(cls, data: bytes) -> AckPayload:
        seq, status = struct.unpack_from(cls._FMT, data)
        return cls(seq, status)


# ---------------------------------------------------------------------------
# Decoded frame
# ---------------------------------------------------------------------------

@dataclass
class DecodedFrame:
    msg_type: int
    seq_num:  int
    payload:  bytes
    crc_ok:   bool


# ---------------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------------

class FrameEncoder:
    """Builds binary frames from message type + payload bytes."""

    def build(self, msg_type: int, seq: int, payload: bytes) -> bytes:
        crc_input = struct.pack('<BHI', msg_type, seq, len(payload)) + payload
        crc = crc16(crc_input)
        return (
            bytes([_START_1, _START_2])
            + struct.pack('<BHI', msg_type, seq, len(payload))
            + payload
            + struct.pack('<H', crc)
            + bytes([_END_1, _END_2])
        )

    def build_image_chunk(self, seq: int, frame_id: int, chunk_idx: int,
                          total_chunks: int, total_size: int,
                          jpeg_data: bytes) -> bytes:
        header = ImageChunkHeader(frame_id, chunk_idx, total_chunks, total_size)
        return self.build(CamMsg.IMAGE_CHUNK, seq, header.pack() + jpeg_data)

    def build_control_ref(self, seq: int,
                          payload: ControlRefPayload) -> bytes:
        return self.build(RobotMsg.CONTROL_REF, seq, payload.pack())

    def build_ack(self, seq: int, acked_seq: int, status: int) -> bytes:
        return self.build(CamMsg.ACK, seq,
                          AckPayload(acked_seq, status).pack())

    def build_heartbeat(self, seq: int, msg_type: int = RobotMsg.HEARTBEAT) -> bytes:
        return self.build(msg_type, seq, b'')


# ---------------------------------------------------------------------------
# Streaming decoder
# ---------------------------------------------------------------------------

class FrameDecoder:
    """Feed raw bytes, yield DecodedFrame objects."""

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
            if buf[0] == _START_1 and buf[1] == _START_2:
                break
            buf.pop(0)

        if len(buf) < 9:
            return None

        msg_type, seq_num, payload_len = struct.unpack_from('<BHI', buf, 2)
        total_len = _MIN_FRAME + payload_len

        if len(buf) < total_len:
            return None

        if buf[total_len - 2] != _END_1 or buf[total_len - 1] != _END_2:
            del buf[0]
            return None

        payload     = bytes(buf[9: 9 + payload_len])
        crc_stored, = struct.unpack_from('<H', buf, 9 + payload_len)

        crc_input = struct.pack('<BHI', msg_type, seq_num, payload_len) + payload
        crc_ok    = crc16(crc_input) == crc_stored

        del buf[:total_len]
        return DecodedFrame(msg_type, seq_num, payload, crc_ok)
