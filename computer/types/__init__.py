"""
computer.types — shared interfaces and pure data types.

No I/O, no threading, no business logic.
"""

from .signals    import Frame, ControlSignal
from .detections import Detection, FrameResult
from .observers  import (
    FrameObserver, ControlObserver, ResultObserver,
    FrameObservable, ControlObservable, ResultObservable,
)
from .transport  import Transport

__all__ = [
    "Frame", "ControlSignal",
    "Detection", "FrameResult",
    "FrameObserver", "ControlObserver", "ResultObserver",
    "FrameObservable", "ControlObservable", "ResultObservable",
    "Transport",
]
