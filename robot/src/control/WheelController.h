#pragma once
// =============================================================================
// robot/src/control/WheelController.h — differential-drive motor controller.
//
// Accepts a ControlRefPayload (angle_deg + speed_ref) from the communication
// layer and translates it to per-wheel PWM commands, enforcing a rate-limiter
// to prevent abrupt changes that could topple cargo.
//
// Wheel power formula (SPEC.md §4.2):
//   rad   = radians(angle_deg)
//   fwd   = speed_ref * cos(rad)
//   turn  = speed_ref * sin(rad)
//   left  = clamp(fwd - turn, -1, 1)
//   right = clamp(fwd + turn, -1, 1)
//
// Rate limiter (SPEC.md §4.3):
//   MAX_DELTA_PER_TICK = 0.02  at  CONTROL_HZ = 50
//   → 1.0 s ramp from 0 to full speed
// =============================================================================

#include <Arduino.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "../types/Protocol.h"
#include "../types/MotorTypes.h"

class WheelController {
public:
    // -------------------------------------------------------------------------
    // Tuning constants
    // -------------------------------------------------------------------------
    static constexpr float MAX_DELTA_PER_TICK = 0.02f;  // max power change per tick
    static constexpr int   CONTROL_HZ         = 50;     // update() call frequency

    // -------------------------------------------------------------------------
    // Construction
    // -------------------------------------------------------------------------
    WheelController(WheelPins left, WheelPins right);

    // Configure LEDC PWM channels and GPIO directions.
    void begin();

    // -------------------------------------------------------------------------
    // Reference input — called from BT receive context (any task)
    // -------------------------------------------------------------------------

    // Set the desired motion reference. Thread-safe (mutex-protected).
    void setRef(const Protocol::ControlRefPayload& ref);

    // -------------------------------------------------------------------------
    // Control loop — call from a dedicated FreeRTOS task at CONTROL_HZ
    // -------------------------------------------------------------------------

    // 1. Read current reference atomically.
    // 2. Compute target wheel speeds (_computeTargets).
    // 3. Slew actual speeds toward targets (rate limiter).
    // 4. Write PWM to H-bridge.
    void update();

    // Immediate hardware stop — bypasses the rate limiter.
    // Use only for emergency / safety shutdowns.
    void emergencyStop();

    // Diagnostics (no mutex needed — floats are atomic on Xtensa)
    float currentLeft()  const { return _current_left;  }
    float currentRight() const { return _current_right; }

private:
    WheelSpeeds _computeTargets(float angle_deg, float speed_ref) const;
    void        _driveMotor(const WheelPins& pins, uint8_t channel, float power);

    static float _clamp(float v, float lo, float hi) {
        return v < lo ? lo : (v > hi ? hi : v);
    }

    // -------------------------------------------------------------------------
    // Hardware configuration
    // -------------------------------------------------------------------------
    WheelPins _left;
    WheelPins _right;

    static constexpr uint8_t LEFT_CHANNEL  = 2;
    static constexpr uint8_t RIGHT_CHANNEL = 3;
    static constexpr uint32_t PWM_FREQ     = 5000;   // Hz
    static constexpr uint8_t  PWM_RES_BITS = 8;      // 0–255

    // -------------------------------------------------------------------------
    // State — reference (written by BT task, read by control task)
    // -------------------------------------------------------------------------
    SemaphoreHandle_t          _ref_mutex;
    Protocol::ControlRefPayload _ref { 0.0f, 0.0f };  // safe initial state: stopped

    // -------------------------------------------------------------------------
    // State — current (smoothed) wheel powers (only written by control task)
    // -------------------------------------------------------------------------
    float _current_left  { 0.0f };
    float _current_right { 0.0f };
};
