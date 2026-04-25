"""
computer.types.observers — Observer pattern ABCs and Observable mixins.

Observer ABCs define the consumer interface (on_* methods).
Observable mixins implement the subscription mechanism for producers.

Usage
-----
A class that *produces* Frame events inherits FrameObservable and calls
_notify_frame(frame) whenever a Frame is ready.

A class that *consumes* Frame events inherits FrameObserver and
implements on_frame(frame).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .signals    import Frame, ControlSignal
from .detections import FrameResult


# ── Observers (consumers) ────────────────────────────────────────────────────

class FrameObserver(ABC):
    @abstractmethod
    def on_frame(self, frame: Frame) -> None: ...


class ControlObserver(ABC):
    @abstractmethod
    def on_control(self, signal: ControlSignal) -> None: ...


class ResultObserver(ABC):
    @abstractmethod
    def on_result(self, result: FrameResult) -> None: ...


# ── Observables (producers — cooperative mixin) ───────────────────────────────

class FrameObservable:
    """Mixin for classes that produce Frame events."""

    def __init__(self) -> None:
        self._frame_observers: list[FrameObserver] = []

    def add_frame_observer(self, obs: FrameObserver) -> None:
        self._frame_observers.append(obs)

    def _notify_frame(self, frame: Frame) -> None:
        for obs in self._frame_observers:
            obs.on_frame(frame)


class ControlObservable:
    """Mixin for classes that produce ControlSignal events."""

    def __init__(self) -> None:
        self._control_observers: list[ControlObserver] = []

    def add_control_observer(self, obs: ControlObserver) -> None:
        self._control_observers.append(obs)

    def _notify_control(self, signal: ControlSignal) -> None:
        for obs in self._control_observers:
            obs.on_control(signal)


class ResultObservable:
    """Mixin for classes that produce FrameResult events."""

    def __init__(self) -> None:
        self._result_observers: list[ResultObserver] = []

    def add_result_observer(self, obs: ResultObserver) -> None:
        self._result_observers.append(obs)

    def _notify_result(self, result: FrameResult) -> None:
        for obs in self._result_observers:
            obs.on_result(result)
