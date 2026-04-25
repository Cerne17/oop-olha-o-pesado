"""
computer.vision.detectors.base — Detector abstract base class.

Implement this ABC for each detection strategy.
See SPEC.md §7.1 for the contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from computer.types.detections import Detection


class Detector(ABC):
    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[Detection]:
        """
        frame : np.ndarray — BGR image, shape (H, W, 3), dtype uint8.
        Returns zero or more Detection objects.
        """
        ...
