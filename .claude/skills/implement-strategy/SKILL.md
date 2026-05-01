# Skill: Implement a control strategy

## Objective
Create a concrete `ResultObserver + ControlObservable` strategy that converts
`FrameResult` detections into a `ControlSignal` and passes it to `RobotSender`.

## Key files
| File | Role |
|------|------|
| `computer/vision/strategy.py` | `BlobFollowerStrategy` stub — implement here |
| `computer/types/observers.py` | `ResultObserver`, `ControlObservable` ABCs + mixins |
| `computer/types/signals.py` | `ControlSignal(angle_deg, speed_ref)` |
| `computer/types/detections.py` | `FrameResult`, `Detection` |
| `computer/main.py` | Observer wiring in `_run_autonomous()` lines 67–69 |

## Spec reference
SPEC.md §7.4 (BlobFollowerStrategy), §5 (ControlSignal semantics)

## Steps

### 1. Understand ControlSignal
`computer/types/signals.py`:
```python
@dataclass(frozen=True)
class ControlSignal:
    angle_deg: float   # [-180.0, 180.0] clockwise from straight forward
    speed_ref: float   # [-1.0, 1.0]   negative = reverse

    @classmethod
    def stopped(cls) -> ControlSignal:
        return cls(angle_deg=0.0, speed_ref=0.0)
```
The robot's `WheelController` converts this to left/right motor powers:
```
fwd   = speed_ref * cos(radians(angle_deg))
turn  = speed_ref * sin(radians(angle_deg))
left  = clamp(fwd - turn, -1, 1)
right = clamp(fwd + turn, -1, 1)
```

### 2. Implement `BlobFollowerStrategy.on_result`
`computer/vision/strategy.py:36` currently raises `NotImplementedError`.

```python
def on_result(self, result: FrameResult) -> None:
    if not result.detections:
        self._notify_control(ControlSignal.stopped())
        return

    # Pick the largest detection
    best = max(result.detections, key=lambda d: d.area)

    # Compute steering: how far off-centre is the target?
    cx, _ = best.centre
    offset = cx - (self._frame_width / 2.0)              # pixels, + = right
    angle_deg = (offset / (self._frame_width / 2.0)) * self._steer_gain

    signal = ControlSignal(
        angle_deg = max(-180.0, min(180.0, angle_deg)),
        speed_ref = self._base_speed,
    )
    self._notify_control(signal)
```

### 3. Add a new strategy (alternative)
To create a completely different strategy, add a new file:
`computer/vision/my_strategy.py`:

```python
from __future__ import annotations
from computer.types.observers  import ResultObserver, ControlObservable
from computer.types.detections import FrameResult
from computer.types.signals    import ControlSignal


class MyStrategy(ResultObserver, ControlObservable):
    def __init__(self, ...) -> None:
        ResultObserver.__init__(self)
        ControlObservable.__init__(self)
        # store config

    def on_result(self, result: FrameResult) -> None:
        # compute signal
        signal = ControlSignal(angle_deg=..., speed_ref=...)
        self._notify_control(signal)
```

Both parent `__init__` calls are required — the mixin constructors initialise
the observer lists.

### 4. Wire in `computer/main.py`
Replace `BlobFollowerStrategy` in `_run_autonomous()`:
```python
strategy = MyStrategy(...)
processor.add_result_observer(strategy)
strategy.add_control_observer(robot_sender)
```

## Invariants
- `on_result()` is called **synchronously from `vision-worker`**. It must
  return quickly — do not block, sleep, or do I/O.
- Always call `_notify_control()` even when there are no detections (emit
  `ControlSignal.stopped()`), otherwise the robot continues at the last speed.
- `angle_deg` must stay in `[-180.0, 180.0]` and `speed_ref` in `[-1.0, 1.0]`.
  Values outside these ranges are not clipped by the firmware — they will
  produce incorrect wheel powers.
- Call both parent `__init__` explicitly. Relying on MRO alone will miss the
  second parent's initialisation.

## Verification
Add a temporary print in `on_result()`:
```python
print(f"[STRATEGY] detections={len(result.detections)} signal={signal}")
```
Run Phase 3 and point the camera at a target. The angle should track the
target's horizontal position and reach ~0 when the target is centred.
