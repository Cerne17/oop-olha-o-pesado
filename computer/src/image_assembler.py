"""
image_assembler.py — Reassembles chunked JPEG frames received over Bluetooth.

The ESP32 splits each JPEG image into fixed-size chunks (512 bytes each).
ImageAssembler buffers incoming ImageChunkHeader + data pairs and emits a
complete JPEG bytes object once all chunks for a frame have arrived.

Design decisions:
- Frames can arrive out of order across chunks (e.g., chunk 2 before chunk 1),
  so we use a dict keyed by chunk_idx.
- Old incomplete frames are evicted after a configurable timeout to avoid
  memory accumulation when chunks are dropped.
- The assembler is not thread-safe on its own; the caller must serialise access
  (CommunicationModule handles this via its receive loop).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from protocol import ImageChunkHeader


# ---------------------------------------------------------------------------
# Internal per-frame state
# ---------------------------------------------------------------------------
@dataclass
class _FrameBuffer:
    frame_id:     int
    total_chunks: int
    total_size:   int
    chunks:       dict[int, bytes] = field(default_factory=dict)
    created_at:   float = field(default_factory=time.monotonic)

    def add_chunk(self, chunk_idx: int, data: bytes) -> None:
        self.chunks[chunk_idx] = data

    @property
    def is_complete(self) -> bool:
        return len(self.chunks) == self.total_chunks

    def assemble(self) -> bytes:
        return b''.join(self.chunks[i] for i in range(self.total_chunks))


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------
class ImageAssembler:
    """
    Feed image chunk payloads (header + raw bytes) into on_chunk().
    Register a callback via on_frame_ready() to receive complete JPEG buffers.

    Parameters
    ----------
    frame_timeout_s : float
        Incomplete frames older than this are discarded (default: 2 s).
    """

    def __init__(self, frame_timeout_s: float = 2.0) -> None:
        self._timeout  = frame_timeout_s
        self._buffers: dict[int, _FrameBuffer] = {}
        self._callback: Optional[Callable[[int, bytes], None]] = None

    def on_frame_ready(self, callback: Callable[[int, bytes], None]) -> None:
        """
        Register a callback that is invoked when a complete frame is assembled.

        Parameters
        ----------
        callback : (frame_id: int, jpeg_bytes: bytes) -> None
        """
        self._callback = callback

    def on_chunk(self, header: ImageChunkHeader, jpeg_chunk: bytes) -> None:
        """
        Process one received image chunk.  Call this for every IMAGE_CHUNK
        message received from the transport.
        """
        # Evict stale incomplete frames first
        self._evict_stale()

        fid = header.frame_id

        # Create buffer for a new frame
        if fid not in self._buffers:
            self._buffers[fid] = _FrameBuffer(
                frame_id     = fid,
                total_chunks = header.total_chunks,
                total_size   = header.total_size,
            )

        buf = self._buffers[fid]

        # Ignore duplicate chunks
        if header.chunk_idx in buf.chunks:
            return

        buf.add_chunk(header.chunk_idx, jpeg_chunk)

        if buf.is_complete:
            jpeg = buf.assemble()
            del self._buffers[fid]

            if self._callback:
                self._callback(fid, jpeg)

    def _evict_stale(self) -> None:
        now = time.monotonic()
        stale = [
            fid for fid, buf in self._buffers.items()
            if now - buf.created_at > self._timeout
        ]
        for fid in stale:
            buf = self._buffers.pop(fid)
            received = len(buf.chunks)
            print(f"[ASSEMBLER] Evicted stale frame {fid} "
                  f"({received}/{buf.total_chunks} chunks received)")

    @property
    def pending_frame_count(self) -> int:
        return len(self._buffers)
