"""
protocol.py — Python mirror of the ESP32 Protocol.h binary protocol.

Frame layout (all multi-byte fields little-endian):

  [0xCA][0xFE]   start magic    (2 bytes)
  [MSG_TYPE]     message type   (1 byte,  uint8)
  [SEQ_NUM]      sequence num   (2 bytes, uint16-LE)
  [PAYLOAD_LEN]  payload length (4 bytes, uint32-LE)
  [PAYLOAD]      variable
  [CRC16]        CRC-16/CCITT   (2 bytes, uint16-LE)
  [0xED][0xED]   end magic      (2 bytes)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FRAME_START = b'\xCA\xFE'
FRAME_END   = b'\xED\xED'

HEADER_SIZE  = 9   # start(2) + type(1) + seq(2) + len(4)
FOOTER_SIZE  = 4   # crc(2) + end(2)
OVERHEAD     = HEADER_SIZE + FOOTER_SIZE

IMAGE_CHUNK_DATA_SIZE = 512   # bytes per chunk (must match ESP32)


# ---------------------------------------------------------------------------
# Message types
# ---------------------------------------------------------------------------
class MsgType(IntEnum):
    IMAGE_CHUNK   = 0x01
    TELEMETRY     = 0x02
    WHEEL_CONTROL = 0x03
    ACK           = 0x04
    HEARTBEAT     = 0x05


# ---------------------------------------------------------------------------
# Payload dataclasses
# ---------------------------------------------------------------------------
@dataclass
class ImageChunkHeader:
    frame_id:     int   # uint16
    chunk_idx:    int   # uint16
    total_chunks: int   # uint16
    total_size:   int   # uint32

    # '<HHHi' would be wrong — 'I' for unsigned 32-bit
    _FMT = '<HHHI'
    SIZE = struct.calcsize(_FMT)

    def pack(self) -> bytes:
        return struct.pack(self._FMT,
                           self.frame_id, self.chunk_idx,
                           self.total_chunks, self.total_size)

    @classmethod
    def unpack(cls, data: bytes) -> 'ImageChunkHeader':
        fid, cidx, total, sz = struct.unpack_from(cls._FMT, data)
        return cls(fid, cidx, total, sz)


@dataclass
class TelemetryPayload:
    left_rpm:     float
    right_rpm:    float
    speed_mps:    float
    timestamp_ms: int   # uint32

    _FMT = '<fffI'
    SIZE = struct.calcsize(_FMT)

    def pack(self) -> bytes:
        return struct.pack(self._FMT,
                           self.left_rpm, self.right_rpm,
                           self.speed_mps, self.timestamp_ms)

    @classmethod
    def unpack(cls, data: bytes) -> 'TelemetryPayload':
        lr, rr, sp, ts = struct.unpack_from(cls._FMT, data)
        return cls(lr, rr, sp, ts)


@dataclass
class WheelControlPayload:
    left_power:  float   # [-1.0, 1.0]
    right_power: float   # [-1.0, 1.0]

    _FMT = '<ff'
    SIZE = struct.calcsize(_FMT)

    def pack(self) -> bytes:
        return struct.pack(self._FMT, self.left_power, self.right_power)

    @classmethod
    def unpack(cls, data: bytes) -> 'WheelControlPayload':
        lp, rp = struct.unpack_from(cls._FMT, data)
        return cls(lp, rp)


@dataclass
class AckPayload:
    acked_seq: int    # uint16
    status:    int    # uint8  (0=OK, 1=CRC_ERROR, 2=UNKNOWN_TYPE)

    _FMT = '<HB'
    SIZE = struct.calcsize(_FMT)

    def pack(self) -> bytes:
        return struct.pack(self._FMT, self.acked_seq, self.status)

    @classmethod
    def unpack(cls, data: bytes) -> 'AckPayload':
        seq, st = struct.unpack_from(cls._FMT, data)
        return cls(seq, st)


# ---------------------------------------------------------------------------
# CRC-16/CCITT (XModem) — polynomial 0x1021, init 0x0000
# Must match the crc16() function in Protocol.h
# ---------------------------------------------------------------------------
def crc16(data: bytes) -> int:
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
        crc &= 0xFFFF
    return crc


# ---------------------------------------------------------------------------
# Frame encoder
# ---------------------------------------------------------------------------
class FrameEncoder:
    """Stateless encoder — builds a complete binary frame."""

    def __init__(self) -> None:
        self._seq: int = 0

    def encode(self, msg_type: MsgType, payload: bytes = b'') -> bytes:
        seq = self._seq
        self._seq = (self._seq + 1) & 0xFFFF

        # CRC input: type(1) + seq(2) + len(4) + payload
        crc_input = struct.pack('<BHI', int(msg_type), seq, len(payload)) + payload
        checksum = crc16(crc_input)

        frame = (
            FRAME_START
            + struct.pack('<BHI', int(msg_type), seq, len(payload))
            + payload
            + struct.pack('<H', checksum)
            + FRAME_END
        )
        return frame

    # ---- convenience helpers ------------------------------------------------

    def encode_wheel_control(self, left: float, right: float) -> bytes:
        return self.encode(MsgType.WHEEL_CONTROL,
                           WheelControlPayload(left, right).pack())

    def encode_heartbeat(self) -> bytes:
        return self.encode(MsgType.HEARTBEAT)

    def encode_ack(self, acked_seq: int, status: int = 0) -> bytes:
        return self.encode(MsgType.ACK, AckPayload(acked_seq, status).pack())


# ---------------------------------------------------------------------------
# Frame decoder (streaming state machine)
# ---------------------------------------------------------------------------
@dataclass
class DecodedFrame:
    msg_type: MsgType
    seq_num:  int
    payload:  bytes


class FrameDecoder:
    """
    Feed raw bytes from the transport into feed().  Complete decoded frames
    are returned as a list of DecodedFrame objects.  Handles stream
    fragmentation gracefully.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[DecodedFrame]:
        self._buf.extend(data)
        frames: list[DecodedFrame] = []

        while True:
            frame = self._try_extract()
            if frame is None:
                break
            frames.append(frame)

        return frames

    def _try_extract(self) -> Optional[DecodedFrame]:
        # Find start magic
        start = self._buf.find(FRAME_START)
        if start == -1:
            self._buf.clear()
            return None
        if start > 0:
            del self._buf[:start]   # discard junk before start

        # Need at least HEADER_SIZE bytes
        if len(self._buf) < HEADER_SIZE:
            return None

        # Parse header
        msg_type_raw, seq, payload_len = struct.unpack_from('<BHI', self._buf, 2)

        # Sanity check
        if payload_len > 65536:
            del self._buf[:2]       # skip this start marker and retry
            return None

        total_frame_len = OVERHEAD + payload_len
        if len(self._buf) < total_frame_len:
            return None  # wait for more data

        # Extract payload + footer
        payload_start = HEADER_SIZE
        payload_end   = HEADER_SIZE + payload_len
        payload       = bytes(self._buf[payload_start:payload_end])

        crc_received, = struct.unpack_from('<H', self._buf, payload_end)
        end_bytes = bytes(self._buf[payload_end + 2 : payload_end + 4])

        if end_bytes != FRAME_END:
            # Malformed — skip start marker and retry
            del self._buf[:2]
            return None

        # Verify CRC
        crc_input = bytes(self._buf[2 : payload_end])   # type + seq + len + payload
        if crc16(crc_input) != crc_received:
            del self._buf[:2]
            return None

        # Consume the frame from the buffer
        del self._buf[:total_frame_len]

        try:
            msg_type = MsgType(msg_type_raw)
        except ValueError:
            return None   # unknown type, skip silently

        return DecodedFrame(msg_type=msg_type, seq_num=seq, payload=payload)
