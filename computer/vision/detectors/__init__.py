"""
computer.vision.detectors — pluggable detector implementations.
"""

from .base        import Detector
from .colour_blob import ColourBlobDetector

__all__ = ["Detector", "ColourBlobDetector"]
