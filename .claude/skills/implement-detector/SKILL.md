# Skill: Implement a vision detector

## Objective
Create a concrete `Detector` subclass that analyses a BGR frame and returns
`Detection` objects. Register it with `VisionProcessor` so detections flow
through the observer chain to the robot.

## Key files
| File | Role |
|------|------|
| `computer/vision/detectors/base.py` | `Detector` ABC — the only interface to implement |
| `computer/vision/detectors/colour_blob.py` | Stub reference — implement here first |
| `computer/vision/detectors/__init__.py` | Re-exports `ColourBlobDetector` |
| `computer/vision/processor.py` | `VisionProcessor` — calls `detect()` and notifies observers |
| `computer/types/detections.py` | `Detection`, `FrameResult` dataclasses |
| `computer/main.py` | Where detectors are instantiated and registered (lines 59–64) |

## Spec reference
SPEC.md §7.1 (Detector contract), §7.2 (ColourBlobDetector)

## Steps

### 1. Read the ABC
`computer/vision/detectors/base.py`:
```python
class Detector(ABC):
    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[Detection]:
        # frame: BGR image, shape (H, W, 3), dtype uint8
        ...
```
Your class must implement exactly this method.

### 2. Read the `Detection` dataclass
`computer/types/detections.py`:
```python
@dataclass
class Detection:
    label:      str
    confidence: float                    # [0.0, 1.0]
    bbox:       tuple[int,int,int,int]   # (x, y, w, h) in pixels

    @property
    def centre(self) -> tuple[float, float]: ...
    @property
    def area(self) -> int: ...
```

### 3. Create the detector file
Add a new file in `computer/vision/detectors/`. Name it after the strategy,
e.g. `computer/vision/detectors/my_detector.py`:

```python
from __future__ import annotations

import numpy as np
from computer.types.detections import Detection
from .base import Detector


class MyDetector(Detector):
    def __init__(self, label: str, ...) -> None:
        self._label = label
        # store config

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results: list[Detection] = []
        # --- your detection logic here ---
        # example:
        #   mask = cv2.inRange(hsv, low, high)
        #   contours, _ = cv2.findContours(mask, ...)
        #   for cnt in contours:
        #       x, y, w, h = cv2.boundingRect(cnt)
        #       results.append(Detection(self._label, confidence, (x, y, w, h)))
        return results
```

### 4. Export from the package
Add to `computer/vision/detectors/__init__.py`:
```python
from .my_detector import MyDetector
```

### 5. Register in `computer/main.py`
In `_run_autonomous()` (around line 59):
```python
processor.add_detector(MyDetector(
    label = "my_target",
    # your config params
))
```
Multiple detectors can be registered; `VisionProcessor` will call each in
order and merge their results into a single `FrameResult`.

### 6. Implement `VisionProcessor._worker_loop`
`computer/vision/processor.py:70` currently raises `NotImplementedError`.
This must be implemented before any detector is useful. The loop must:
1. Dequeue a `Frame` from `self._frame_queue`
2. Decode JPEG → BGR numpy array (use `cv2.imdecode`)
3. Call `detect()` on each registered detector
4. Build a `FrameResult` from the detections
5. Call `self._notify_result(result)`

Minimal implementation:
```python
def _worker_loop(self) -> None:
    import cv2
    while not self._stop_event.is_set():
        try:
            frame = self._frame_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        arr = cv2.imdecode(np.frombuffer(frame.jpeg, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            continue
        detections = []
        for det in self._detectors:
            detections.extend(det.detect(arr))
        result = FrameResult(frame_id=frame.frame_id, detections=detections)
        if self._show_preview:
            cv2.imshow("preview", arr)
            cv2.waitKey(1)
        self._notify_result(result)
```

## Invariants
- `detect()` must be **stateless and thread-safe** — it will be called from
  `vision-worker` only, but the instance may be shared in future.
- `detect()` must never raise — catch exceptions internally and return `[]`.
- `bbox` must use `(x, y, w, h)` pixel coordinates, not normalised values.
- Do not import `computer.main` or `computer.communication` from a detector.

## Verification
```bash
# Phase 3 with a static test image:
python -m computer.main --phase 3
# Inspect FrameResult.detections in a temporary print inside _worker_loop
```
