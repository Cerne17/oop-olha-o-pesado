# Skill: Add a new motion mode to WheelController

## Objective
Extend `WheelController` with a new motion behaviour — for example, spin-in-place,
crab steering, or speed-capped forward-only mode — without breaking the existing
`CONTROL_REF` pipeline.

## Key files
| File | Role |
|------|------|
| `robot/src/control/WheelController.h` | Class declaration, constants |
| `robot/src/control/WheelController.cpp` | `_computeTargets`, `update`, `emergencyStop` |
| `robot/src/types/Protocol.h` | `ControlRefPayload` — the input this controller receives |
| `robot/src/communication/RobotComm.cpp` | Where `setRef()` is called from `_dispatchFrame` |

## Spec reference
SPEC.md §6.2 (wheel power formula), §6.3 (rate limiter)

## Understanding the current flow
```
CONTROL_REF frame arrives
    → RobotComm._dispatchFrame()
    → _wheel.setRef(angle_deg, speed_ref)
    → WheelController._ref updated (atomic under mutex)
    → _controlTask calls update() at 50 Hz
    → update() calls _computeTargets(_ref) → target_left, target_right
    → slew limiter applied to _current_left, _current_right
    → _applyPwm(_current_left, _current_right)
```

## Steps

### 1. Add a mode enum to `WheelController.h`
```cpp
enum class DriveMode : uint8_t {
    NORMAL    = 0,   // existing: fwd/turn blend
    SPIN      = 1,   // spin in place: left = -right
    FORWARD   = 2,   // ignore angle, forward only
};
```

### 2. Add a `setMode()` method
```cpp
// WheelController.h
void setMode(DriveMode mode);

// WheelController.cpp
void WheelController::setMode(DriveMode mode) {
    _mode = mode;
}
```
Store `_mode` as a member with the appropriate type:
```cpp
DriveMode _mode { DriveMode::NORMAL };
```

### 3. Extend `_computeTargets`
```cpp
WheelSpeeds WheelController::_computeTargets(float angle_deg, float speed_ref) const {
    if (speed_ref == 0.0f) return {0.0f, 0.0f};

    float rad  = angle_deg * M_PI / 180.0f;
    float fwd, turn;

    switch (_mode) {
    case DriveMode::SPIN:
        // Ignore angle; spin intensity = speed_ref
        return { -speed_ref, speed_ref };

    case DriveMode::FORWARD:
        // Ignore angle; go straight
        return {
            std::max(-1.0f, std::min(1.0f, speed_ref)),
            std::max(-1.0f, std::min(1.0f, speed_ref))
        };

    default:  // NORMAL
        fwd  = speed_ref * cosf(rad);
        turn = speed_ref * sinf(rad);
        return {
            std::max(-1.0f, std::min(1.0f, fwd - turn)),
            std::max(-1.0f, std::min(1.0f, fwd + turn))
        };
    }
}
```

### 4. Expose mode switching via protocol (optional)
If the mode should be set from the computer, add a new message type
(`CONFIG = 0x04` on Link B) using the `/add-message-type`
skill. If mode switching is only for local testing, call `setMode()` directly
from `robot/src/main.cpp`.

### 5. Mirror the mode logic in the emulator
`emulator/src/simulated_robot.py:_compute_targets` mirrors the C++ formula.
Add the same mode-switching logic there so Phase 1 testing reflects the new
behaviour:
```python
if mode == "spin":
    return -speed_ref, speed_ref
```

## Invariants
- The slew limiter in `update()` is applied AFTER `_computeTargets` and must
  not be bypassed (except by `emergencyStop`). It prevents mechanical shock.
- `emergencyStop()` must always work regardless of mode — zero both `_ref`
  fields and clear `_current_left/_current_right` immediately.
- Keep `MAX_DELTA_PER_TICK = 0.02f` and `CONTROL_HZ = 50` in sync with
  `emulator/src/simulated_robot.py`. These constants define the ramp behaviour.
- Return values from `_computeTargets` must be clamped to `[-1.0, 1.0]` in
  all modes. PWM duty cycle outside this range has undefined hardware behaviour.

## Verification
```bash
# Phase 1: switch to SPIN mode, verify left/right are equal and opposite
python emulator/src/main.py --verbose &
python -m computer.main --phase 1
# Press any arrow key; emulator should show L=-0.XX R=+0.XX
```
Flash and test on the physical robot with `pio run --target upload`.
