"""
image_processor.py — Real-time computer vision pipeline.

ImageProcessor receives complete JPEG frames and runs a configurable
pipeline of detectors / transforms on them.  Results are published via
a callback so the RobotController can act on them without being coupled
to OpenCV.

The class is designed to run in its own thread: frames are queued and
processed asynchronously so the Bluetooth receive loop is never blocked
by heavy CV work.

Extend by:
  1. Subclassing and overriding _process_frame()
  2. Adding a Detector via add_detector()
  3. Replacing the default pipeline entirely with set_pipeline()
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class Detection:
    label:      str
    confidence: float
    bbox:       tuple[int, int, int, int]   # (x, y, w, h)
    extra:      dict[str, Any] = field(default_factory=dict)


@dataclass
class FrameResult:
    frame_id:   int
    detections: list[Detection]
    annotated:  Optional[np.ndarray] = None  # BGR image with overlays drawn


# ---------------------------------------------------------------------------
# Detector interface
# ---------------------------------------------------------------------------
class Detector:
    """
    Base class for a single-pass detector that operates on a decoded BGR frame.
    Override detect() to return a list of Detection objects.
    """
    def detect(self, frame: np.ndarray) -> list[Detection]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Built-in example: simple colour blob detector
# ---------------------------------------------------------------------------
class ColourBlobDetector(Detector):
    """
    Detects blobs of a target colour in HSV space.  Useful as a starting
    point for line-following or target-tracking robots.

    Parameters
    ----------
    label    : str   — label shown on the annotated frame
    hsv_low  : colour lower bound in HSV (H: 0-179, S/V: 0-255)
    hsv_high : colour upper bound in HSV
    min_area : minimum contour area in pixels
    """

    def __init__(self,
                 label:    str,
                 hsv_low:  tuple[int, int, int],
                 hsv_high: tuple[int, int, int],
                 min_area: int = 500) -> None:
        self._label    = label
        self._low      = np.array(hsv_low,  dtype=np.uint8)
        self._high     = np.array(hsv_high, dtype=np.uint8)
        self._min_area = min_area

    def detect(self, frame: np.ndarray) -> list[Detection]:
        hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self._low, self._high)
        mask = cv2.erode(mask,  None, iterations=2)
        mask = cv2.dilate(mask, None, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        detections: list[Detection] = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < self._min_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            confidence  = min(1.0, area / (frame.shape[0] * frame.shape[1]))
            detections.append(Detection(self._label, confidence, (x, y, w, h)))

        return detections


# ---------------------------------------------------------------------------
# Main image processor
# ---------------------------------------------------------------------------
class ImageProcessor:
    """
    Asynchronous image processing pipeline.

    Frames are placed on an internal queue by push_frame() and processed in
    a background thread.  Results are delivered via the callback registered
    with on_result().

    Parameters
    ----------
    max_queue_size : int
        Maximum number of pending frames.  Oldest frame is dropped when full
        so the pipeline never falls too far behind real time.
    show_preview   : bool
        If True, opens a cv2.imshow() window — useful for debugging.
        Requires a display (does not work headless).
    """

    def __init__(self,
                 max_queue_size: int = 4,
                 show_preview:   bool = False) -> None:
        self._queue        = queue.Queue(maxsize=max_queue_size)
        self._show_preview = show_preview
        self._detectors:   list[Detector] = []
        self._callback:    Optional[Callable[[FrameResult], None]] = None
        self._thread:      Optional[threading.Thread] = None
        self._stop_event   = threading.Event()

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------
    def add_detector(self, detector: Detector) -> None:
        self._detectors.append(detector)

    def on_result(self, callback: Callable[[FrameResult], None]) -> None:
        """Register a callback to receive FrameResult objects."""
        self._callback = callback

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------
    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker, name="image-processor", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._show_preview:
            cv2.destroyAllWindows()

    # -------------------------------------------------------------------------
    # Receiving frames
    # -------------------------------------------------------------------------
    def push_frame(self, frame_id: int, jpeg_bytes: bytes) -> None:
        """
        Enqueue a JPEG frame for processing.  Drops the oldest queued frame
        if the queue is full to prevent unbounded lag.
        """
        try:
            self._queue.put_nowait((frame_id, jpeg_bytes))
        except queue.Full:
            try:
                self._queue.get_nowait()   # drop oldest
            except queue.Empty:
                pass
            self._queue.put_nowait((frame_id, jpeg_bytes))

    # -------------------------------------------------------------------------
    # Background worker
    # -------------------------------------------------------------------------
    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                frame_id, jpeg_bytes = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            result = self._process_frame(frame_id, jpeg_bytes)
            if result and self._callback:
                self._callback(result)

            if self._show_preview and result and result.annotated is not None:
                cv2.imshow("Robot Camera", result.annotated)
                cv2.waitKey(1)

    def _process_frame(self,
                       frame_id: int,
                       jpeg_bytes: bytes) -> Optional[FrameResult]:
        # Decode JPEG → BGR numpy array
        np_buf = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        frame  = cv2.imdecode(np_buf, cv2.IMREAD_COLOR)
        if frame is None:
            print(f"[CV] Failed to decode frame {frame_id}")
            return None

        # Run all detectors
        all_detections: list[Detection] = []
        for detector in self._detectors:
            all_detections.extend(detector.detect(frame))

        # Annotate frame
        annotated = frame.copy()
        for det in all_detections:
            x, y, w, h = det.bbox
            cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
            label = f"{det.label} {det.confidence:.0%}"
            cv2.putText(annotated, label, (x, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        return FrameResult(frame_id=frame_id,
                           detections=all_detections,
                           annotated=annotated)
