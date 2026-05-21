"""
computer.types — shared interfaces and pure data types.

No I/O, no threading, no business logic.
"""

from .signals   import Frame, ControlSignal
from .observers import (
    FrameObserver, ControlObserver,
    FrameObservable, ControlObservable,
)
from .transport import Transport

__all__ = [
    "Frame", "ControlSignal",
    "FrameObserver", "ControlObserver",
    "FrameObservable", "ControlObservable",
    "Transport",
]
