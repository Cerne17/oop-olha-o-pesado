"""
computer.vision.strategy — ControlStrategy placeholder.

Converts FrameResult into ControlSignal.
See SPEC.md §7.4 for the full behavioral specification.
"""

from __future__ import annotations

from computer.types.observers  import ResultObserver, ControlObservable
from computer.types.detections import FrameResult


class BlobFollowerStrategy(ResultObserver, ControlObservable):
    """
    Default control strategy: steer toward the largest detected blob.

    Parameters
    ----------
    frame_width : int   — expected frame width in pixels
    steer_gain  : float — max steering angle when target is at frame edge
    base_speed  : float — constant forward speed while a target is tracked
    """

    def __init__(self,
                 frame_width: int   = 320,
                 steer_gain:  float = 90.0,
                 base_speed:  float = 0.5) -> None:
        ResultObserver.__init__(self)
        ControlObservable.__init__(self)
        self._frame_width = frame_width
        self._steer_gain  = steer_gain
        self._base_speed  = base_speed

    # ResultObserver
    def on_result(self, result: FrameResult) -> None:
        raise NotImplementedError(
            "BlobFollowerStrategy.on_result is a placeholder — implement here.\n"
            "See SPEC.md §7.4 for the specification."
        )
