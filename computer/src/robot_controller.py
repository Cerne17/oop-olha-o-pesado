"""
robot_controller.py — Translates CV results into wheel commands.

RobotController receives FrameResult objects from ImageProcessor and
decides the target left/right wheel powers.  It exposes a command queue
that CommunicationModule drains and sends to the ESP32.

Implement your own control strategy by subclassing RobotController and
overriding _compute_command().  The default strategy is a simple
proportional centred-blob follower: it steers toward the largest detected
object and drives forward proportionally to how centred it is.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Optional

from image_processor import FrameResult, Detection
from protocol import WheelControlPayload


@dataclass
class WheelCommand:
    left:  float   # [-1.0, 1.0]
    right: float   # [-1.0, 1.0]

    def as_payload(self) -> WheelControlPayload:
        return WheelControlPayload(self.left, self.right)

    @classmethod
    def stop(cls) -> 'WheelCommand':
        return cls(0.0, 0.0)

    @classmethod
    def forward(cls, speed: float = 0.5) -> 'WheelCommand':
        return cls(speed, speed)


class RobotController:
    """
    Converts vision results into wheel commands.

    Parameters
    ----------
    frame_width  : int   — expected frame width in pixels (used for centring)
    frame_height : int   — expected frame height in pixels
    base_speed   : float — forward speed when target is centred [0.0, 1.0]
    steer_gain   : float — how aggressively to steer toward the target
    """

    def __init__(self,
                 frame_width:  int   = 320,
                 frame_height: int   = 240,
                 base_speed:   float = 0.4,
                 steer_gain:   float = 1.0) -> None:
        self._frame_cx    = frame_width  / 2.0
        self._frame_cy    = frame_height / 2.0
        self._base_speed  = base_speed
        self._steer_gain  = steer_gain

        # Thread-safe queue of commands for CommunicationModule to drain
        self._cmd_queue: queue.Queue[WheelCommand] = queue.Queue(maxsize=2)
        self._lock = threading.Lock()

        # Last telemetry received from the robot (informational)
        self._last_left_rpm:  float = 0.0
        self._last_right_rpm: float = 0.0
        self._last_speed_mps: float = 0.0

        self._running = True

    # -------------------------------------------------------------------------
    # Called by ImageProcessor callback
    # -------------------------------------------------------------------------
    def on_frame_result(self, result: FrameResult) -> None:
        if not self._running:
            return
        cmd = self._compute_command(result)
        # Drop the oldest command if the queue is full (always keep the latest)
        try:
            self._cmd_queue.put_nowait(cmd)
        except queue.Full:
            try:
                self._cmd_queue.get_nowait()
            except queue.Empty:
                pass
            self._cmd_queue.put_nowait(cmd)

    # -------------------------------------------------------------------------
    # Called by CommunicationModule when telemetry arrives
    # -------------------------------------------------------------------------
    def on_telemetry(self, left_rpm: float, right_rpm: float,
                     speed_mps: float, timestamp_ms: int) -> None:
        with self._lock:
            self._last_left_rpm  = left_rpm
            self._last_right_rpm = right_rpm
            self._last_speed_mps = speed_mps

    # -------------------------------------------------------------------------
    # Called by CommunicationModule to get the next command to send
    # -------------------------------------------------------------------------
    def next_command(self, timeout: float = 0.05) -> Optional[WheelCommand]:
        """
        Returns the next pending WheelCommand, or None if the queue is empty
        within the timeout.
        """
        try:
            return self._cmd_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    # -------------------------------------------------------------------------
    # Control strategy — override this in a subclass
    # -------------------------------------------------------------------------
    def _compute_command(self, result: FrameResult) -> WheelCommand:
        if not result.detections:
            # No target visible — stop (or hold last command — your call)
            return WheelCommand.stop()

        # Use the largest detection as the primary target
        target: Detection = max(result.detections,
                                key=lambda d: d.bbox[2] * d.bbox[3])

        x, y, w, h = target.bbox
        target_cx = x + w / 2.0

        # Normalised error: -1.0 (left edge) → 0.0 (centre) → +1.0 (right edge)
        error = (target_cx - self._frame_cx) / self._frame_cx

        # Proportional steering: positive error → turn right (reduce left wheel)
        steer  = self._steer_gain * error
        left   = self._base_speed - steer
        right  = self._base_speed + steer

        # Clamp to [-1, 1]
        left  = max(-1.0, min(1.0, left))
        right = max(-1.0, min(1.0, right))

        return WheelCommand(left, right)

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------
    def stop(self) -> None:
        self._running = False
        self._cmd_queue.put_nowait(WheelCommand.stop())

    # -------------------------------------------------------------------------
    # Telemetry read-out (informational)
    # -------------------------------------------------------------------------
    @property
    def speed_mps(self) -> float:
        return self._last_speed_mps

    @property
    def left_rpm(self) -> float:
        return self._last_left_rpm

    @property
    def right_rpm(self) -> float:
        return self._last_right_rpm
