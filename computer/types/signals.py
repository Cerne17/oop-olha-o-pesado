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
    buzzer: bool      # False: off (silence); True: on (sound)
    leds: int         # one-hot codification: 0b000 (all off), 0b001 (yellow on), 0b010 (green on), 0b100 (red on)

    @classmethod
    def waiting(cls) -> ControlSignal:
        return cls(angle_deg=0.0, speed_ref=0.0, buzzer=False, leds=0b001)
    
    @classmethod
    def lost(cls) -> ControlSignal:
        return cls(angle_deg=0.0, speed_ref=0.0, buzzer=True, leds=0b100)
    
    @classmethod
    def following(cls, angle: float, speed: float) -> ControlSignal:
        return cls(angle_deg=angle, speed_ref=speed, buzzer=False, leds=0b010)
