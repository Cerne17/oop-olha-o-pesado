"""
computer.types.detections — vision result data types.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Detection:
    label:      str
    confidence: float                      # [0.0, 1.0]
    bbox:       tuple[int, int, int, int]  # (x, y, w, h) pixels

    @property
    def centre(self) -> tuple[float, float]:
        x, y, w, h = self.bbox
        return x + w / 2.0, y + h / 2.0

    @property
    def area(self) -> int:
        return self.bbox[2] * self.bbox[3]


@dataclass
class FrameResult:
    frame_id:   int
    detections: list[Detection] = field(default_factory=list)
    annotated:  bytes | None    = None  # optional annotated JPEG for display
