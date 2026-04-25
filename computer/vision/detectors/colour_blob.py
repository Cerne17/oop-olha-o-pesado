"""
computer.vision.detectors.colour_blob — ColourBlobDetector placeholder.

HSV colour-range blob detector.
See SPEC.md §7.2 for the full behavioral specification.
"""

from __future__ import annotations

import numpy as np

from computer.types.detections import Detection
from .base import Detector


class ColourBlobDetector(Detector):
    """
    Detect coloured blobs using an HSV range + contour analysis.

    Parameters
    ----------
    label    : str                  — label applied to each Detection
    hsv_low  : tuple[int, int, int] — lower HSV bound (H: 0-179, S/V: 0-255)
    hsv_high : tuple[int, int, int] — upper HSV bound
    min_area : int                  — minimum contour area in pixels
    """

    def __init__(self,
                 label:    str,
                 hsv_low:  tuple[int, int, int],
                 hsv_high: tuple[int, int, int],
                 min_area: int = 400) -> None:
        self._label    = label
        self._hsv_low  = hsv_low
        self._hsv_high = hsv_high
        self._min_area = min_area

    def detect(self, frame: np.ndarray) -> list[Detection]:
        raise NotImplementedError(
            "ColourBlobDetector is a placeholder — implement detect() here."
        )
