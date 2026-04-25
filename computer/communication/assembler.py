"""
computer.communication.assembler — reassembles IMAGE_CHUNK messages into Frames.

Chunks arrive out-of-order or with gaps (dropped chunks). The assembler
buffers them by frame_id and fires once all chunks for a frame arrive.
Frames incomplete after frame_timeout_s are evicted to prevent memory growth.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from computer.types.signals import Frame
from .protocol import ImageChunkHeader


@dataclass
class _FrameBuffer:
    frame_id:     int
    total_chunks: int
    total_size:   int
    chunks:       dict[int, bytes] = field(default_factory=dict)
    created_at:   float            = field(default_factory=time.monotonic)

    def add_chunk(self, idx: int, data: bytes) -> None:
        self.chunks[idx] = data

    @property
    def is_complete(self) -> bool:
        return len(self.chunks) == self.total_chunks

    def assemble(self) -> bytes:
        return b''.join(self.chunks[i] for i in range(self.total_chunks))


class ImageAssembler:
    def __init__(self, frame_timeout_s: float = 2.0) -> None:
        self._timeout  = frame_timeout_s
        self._buffers: dict[int, _FrameBuffer] = {}

    def on_chunk(self, header: ImageChunkHeader,
                 jpeg_chunk: bytes) -> Frame | None:
        """
        Process one received IMAGE_CHUNK payload.

        Returns a complete Frame when the last chunk arrives.
        Returns None for all intermediate chunks.
        """
        self._evict_stale()

        fid = header.frame_id
        if fid not in self._buffers:
            self._buffers[fid] = _FrameBuffer(
                frame_id     = fid,
                total_chunks = header.total_chunks,
                total_size   = header.total_size,
            )

        buf = self._buffers[fid]
        if header.chunk_idx in buf.chunks:
            return None  # duplicate chunk — silently ignore

        buf.add_chunk(header.chunk_idx, jpeg_chunk)

        if buf.is_complete:
            jpeg = buf.assemble()
            del self._buffers[fid]
            return Frame(frame_id=fid, jpeg=jpeg, timestamp=time.monotonic())

        return None

    def _evict_stale(self) -> None:
        now   = time.monotonic()
        stale = [fid for fid, buf in self._buffers.items()
                 if now - buf.created_at > self._timeout]
        for fid in stale:
            buf = self._buffers.pop(fid)
            print(f"[ASSEMBLER] Evicted stale frame {fid} "
                  f"({len(buf.chunks)}/{buf.total_chunks} chunks)")

    @property
    def pending_frame_count(self) -> int:
        return len(self._buffers)
