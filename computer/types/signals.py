"""
computer.types.signals — core data types exchanged between modules.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    frame_id:  int    # matches ImageChunkHeader.frame_id
    jpeg:      bytes  # complete assembled JPEG
    timestamp: float  # time.monotonic() at assembly completion


@dataclass(frozen=True)
class ControlSignal:
    angle_deg: float  # [-180.0, 180.0] — 0°=forward, 90°=pivot right
    speed_ref: float  # [-1.0, 1.0]     — +1=max forward, 0=stop, -1=max backward

    @classmethod
    def stopped(cls) -> ControlSignal:
        return cls(angle_deg=0.0, speed_ref=0.0)
