"""
computer.vision.processor — VisionProcessor placeholder.

Receives Frame events, runs detectors, emits FrameResult events.
See SPEC.md §7.3 for the full behavioral specification.
"""

from __future__ import annotations

import queue
import threading
from typing import Optional

from computer.types.observers  import FrameObserver, ResultObservable
from computer.types.signals    import Frame
from computer.types.detections import FrameResult
from .detectors.base import Detector


class VisionProcessor(FrameObserver, ResultObservable):
    """
    Parameters
    ----------
    max_queue    : int  — drop oldest frame when queue is full
    show_preview : bool — display annotated frame with cv2.imshow
    """

    def __init__(self,
                 max_queue:    int  = 2,
                 show_preview: bool = False) -> None:
        FrameObserver.__init__(self)
        ResultObservable.__init__(self)
        self._max_queue    = max_queue
        self._show_preview = show_preview
        self._detectors:   list[Detector] = []
        self._frame_queue: queue.Queue[Frame] = queue.Queue(maxsize=max_queue)
        self._stop_event   = threading.Event()
        self._worker: Optional[threading.Thread] = None

    def add_detector(self, detector: Detector) -> None:
        self._detectors.append(detector)

    def start(self) -> None:
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._worker_loop, name="vision-worker", daemon=True
        )
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker:
            self._worker.join(timeout=3.0)

    # FrameObserver
    def on_frame(self, frame: Frame) -> None:
        """Enqueue frame (newest wins — drop oldest if full)."""
        try:
            self._frame_queue.put_nowait(frame)
        except queue.Full:
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._frame_queue.put_nowait(frame)
            except queue.Full:
                pass

    def _worker_loop(self) -> None:
        raise NotImplementedError(
            "VisionProcessor._worker_loop is a placeholder — implement here.\n"
            "See SPEC.md §7.3 for the specification."
        )
