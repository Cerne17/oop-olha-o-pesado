"""
emulator.simulated_robot -- rate-limited wheel model mirroring WheelController.cpp.

Constants and formulas are kept identical to robot/src/control/WheelController.cpp
so that Phase 1 (emulated) and Phase 2 (physical) behaviour match.

Spec reference: emulator/SPEC.md §5.
"""

from __future__ import annotations

import math
import threading

# Keep in sync with robot/src/control/WheelController.h
MAX_DELTA_PER_TICK  = 0.02
CONTROL_HZ          = 50
MAX_RPM             = 150.0
WHEEL_CIRCUMFERENCE = 0.20   # metres


class SimulatedRobot:
    def __init__(self) -> None:
        self._lock           = threading.Lock()
        self._angle_deg:     float = 0.0
        self._speed_ref:     float = 0.0   # [-1.0, 1.0]
        self._current_left:  float = 0.0
        self._current_right: float = 0.0

    # -------------------------------------------------------------------------
    # Reference input
    # -------------------------------------------------------------------------

    def set_ref(self, angle_deg: float, speed_ref: float) -> None:
        with self._lock:
            self._angle_deg = angle_deg
            self._speed_ref = speed_ref

    # -------------------------------------------------------------------------
    # Control tick -- call at CONTROL_HZ
    # -------------------------------------------------------------------------

    def update(self) -> None:
        with self._lock:
            target_l, target_r = self._compute_targets(
                self._angle_deg, self._speed_ref
            )
            self._current_left  = self._slew(self._current_left,  target_l)
            self._current_right = self._slew(self._current_right, target_r)

    # -------------------------------------------------------------------------
    # Internal helpers (mirror WheelController.cpp exactly)
    # -------------------------------------------------------------------------

    @staticmethod
    def _compute_targets(angle_deg: float,
                         speed_ref: float) -> tuple[float, float]:
        if speed_ref == 0.0:
            return 0.0, 0.0
        rad   = math.radians(angle_deg)
        fwd   = speed_ref * math.cos(rad)
        turn  = speed_ref * math.sin(rad)
        left  = max(-1.0, min(1.0, fwd - turn))
        right = max(-1.0, min(1.0, fwd + turn))
        return left, right

    @staticmethod
    def _slew(current: float, target: float) -> float:
        delta = target - current
        delta = max(-MAX_DELTA_PER_TICK, min(MAX_DELTA_PER_TICK, delta))
        return current + delta

    # -------------------------------------------------------------------------
    # Derived outputs
    # -------------------------------------------------------------------------

    @property
    def speed_mps(self) -> float:
        with self._lock:
            avg_power = (self._current_left + self._current_right) / 2.0
        avg_rpm = avg_power * MAX_RPM
        return avg_rpm * WHEEL_CIRCUMFERENCE / 60.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                'angle_deg':     self._angle_deg,
                'speed_ref':     self._speed_ref,
                'current_left':  self._current_left,
                'current_right': self._current_right,
            }
