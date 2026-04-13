"""
robot_controller.py — Translates CV results into direction reference signals.

RobotController receives FrameResult objects from ImageProcessor and decides
the angle and stop flag to send to the ESP32.  The robot's onboard control
loop (WheelController) is responsible for translating that angle into smooth
wheel motion — this class has no knowledge of individual wheel powers.

The default strategy is a proportional centred-blob follower:
  - No detection visible → stop
  - Blob to the left  → negative angle (steer left)
  - Blob to the right → positive angle (steer right)
  - Blob centred      → angle ≈ 0 (straight forward)

To implement a different strategy (e.g. the hand-sign activator that another
developer is working on), subclass RobotController and override
_compute_direction().
"""

from __future__ import annotations

import math
import queue
import threading
from dataclasses import dataclass
from typing import Optional

from image_processor import FrameResult, Detection
from protocol import DirectionRefPayload


@dataclass
class DirectionCommand:
    """
    High-level movement intent produced by the computer's CV pipeline.

    angle_deg : direction angle sent to the robot (see DirectionRefPayload).
    stop      : when True the robot should come to a smooth stop.
    """
    angle_deg: float
    stop:      bool

    def as_payload(self) -> DirectionRefPayload:
        return DirectionRefPayload(self.angle_deg, self.stop)

    @classmethod
    def stopped(cls) -> 'DirectionCommand':
        return cls(angle_deg=0.0, stop=True)

    @classmethod
    def forward(cls) -> 'DirectionCommand':
        return cls(angle_deg=0.0, stop=False)


class RobotController:
    """
    Converts vision results into DirectionCommand objects.

    Parameters
    ----------
    frame_width  : int   — expected frame width in pixels (used for centring calc)
    steer_gain   : float — max steering angle produced when the target is at the
                           frame edge (degrees).  Default 90° = pivot at edge.
    """

    def __init__(self,
                 frame_width: int   = 320,
                 steer_gain:  float = 90.0) -> None:
        self._frame_cx   = frame_width / 2.0
        self._steer_gain = steer_gain

        # Thread-safe queue of commands for CommunicationModule to drain
        self._cmd_queue: queue.Queue[DirectionCommand] = queue.Queue(maxsize=2)
        self._running = True

    # -------------------------------------------------------------------------
    # Called by ImageProcessor callback
    # -------------------------------------------------------------------------
    def on_frame_result(self, result: FrameResult) -> None:
        if not self._running:
            return
        cmd = self._compute_direction(result)
        # Always keep only the latest command — drop the oldest if full
        try:
            self._cmd_queue.put_nowait(cmd)
        except queue.Full:
            try:
                self._cmd_queue.get_nowait()
            except queue.Empty:
                pass
            self._cmd_queue.put_nowait(cmd)

    # -------------------------------------------------------------------------
    # Called by CommunicationModule to get the next command to send
    # -------------------------------------------------------------------------
    def next_command(self, timeout: float = 0.05) -> Optional[DirectionCommand]:
        try:
            return self._cmd_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    # -------------------------------------------------------------------------
    # Direction strategy — override this in a subclass
    # -------------------------------------------------------------------------
    def _compute_direction(self, result: FrameResult) -> DirectionCommand:
        if not result.detections:
            # No target visible: stop the robot
            return DirectionCommand.stopped()

        # Use the largest detection as the primary tracking target
        target: Detection = max(result.detections,
                                key=lambda d: d.bbox[2] * d.bbox[3])

        x, y, w, h = target.bbox
        target_cx = x + w / 2.0

        # Normalised horizontal error: -1.0 (left edge) → 0.0 (centre) → +1.0 (right edge)
        error = (target_cx - self._frame_cx) / self._frame_cx

        # Map error to angle: positive error → target is to the right → steer right (+)
        angle_deg = error * self._steer_gain

        return DirectionCommand(angle_deg=angle_deg, stop=False)

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------
    def stop(self) -> None:
        self._running = False
        try:
            self._cmd_queue.put_nowait(DirectionCommand.stopped())
        except queue.Full:
            pass
