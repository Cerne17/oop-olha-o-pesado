"""
emulator.image_generator — synthetic JPEG frame generation.

Modes
-----
static : grey frame with crosshair — minimal, verifies framing only
blob   : moving red circle — exercises the computer-side ColourBlobDetector
files  : cycles through JPEG files in a directory — real-world images
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import cv2
import numpy as np


class ImageGenerator:
    def __init__(self, mode: str = 'blob',
                 image_dir: str | None = None,
                 quality:   int        = 80) -> None:
        self._mode          = mode
        self._quality       = quality
        self._frame_counter = 0
        self._file_paths: list[Path] = []
        self._file_index    = 0

        if mode == 'files':
            if not image_dir:
                raise ValueError("--image-dir is required for --mode=files")
            self._file_paths = sorted(
                p for p in Path(image_dir).iterdir()
                if p.suffix.lower() in ('.jpg', '.jpeg')
            )
            if not self._file_paths:
                raise ValueError(f"No JPEG files found in {image_dir}")

    def next_jpeg(self) -> bytes:
        if self._mode == 'static':
            return self._static_frame()
        if self._mode == 'blob':
            return self._blob_frame()
        if self._mode == 'files':
            return self._files_frame()
        raise ValueError(f"Unknown mode: {self._mode!r}")

    # -------------------------------------------------------------------------
    # Frame generators
    # -------------------------------------------------------------------------

    def _encode(self, frame: np.ndarray) -> bytes:
        _, jpeg = cv2.imencode(
            '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self._quality]
        )
        return jpeg.tobytes()

    def _static_frame(self) -> bytes:
        frame = np.full((240, 320, 3), 128, dtype=np.uint8)
        cv2.line(frame, (160, 0),   (160, 240), (255, 255, 255), 1)
        cv2.line(frame, (0,   120), (320, 120), (255, 255, 255), 1)
        return self._encode(frame)

    def _blob_frame(self) -> bytes:
        t  = time.monotonic()
        cx = int(160 + 100 * math.cos(t * 0.5))
        cy = int(120 +  60 * math.sin(t * 0.7))

        frame = np.full((240, 320, 3), (30, 30, 30), dtype=np.uint8)
        cv2.circle(frame, (cx, cy), 30, (0, 0, 200), -1)   # red blob (BGR)

        label = f"f={self._frame_counter}  t={t:.1f}"
        cv2.putText(frame, label, (5, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

        self._frame_counter = (self._frame_counter + 1) & 0xFFFF
        return self._encode(frame)

    def _files_frame(self) -> bytes:
        path = self._file_paths[self._file_index]
        self._file_index = (self._file_index + 1) % len(self._file_paths)
        return path.read_bytes()
