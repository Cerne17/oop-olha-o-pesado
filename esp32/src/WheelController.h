#pragma once
// =============================================================================
// WheelController.h — Differential-drive wheel controller with onboard
//                     smooth-motion control loop.
//
// The computer sends a high-level DirectionRefPayload (angle + stop flag).
// This class is responsible for translating that reference signal into
// per-wheel PWM commands while enforcing smooth acceleration / deceleration,
// so the robot never makes abrupt changes that could topple its cargo.
//
// Architecture
// ─────────────
//   setDirectionRef()  ← called by RobotComm when DIRECTION_REF arrives
//        │
//        ▼
//   _target_left / _target_right  (desired wheel powers, protected by mutex)
//        │
//   update()  ← called by a dedicated FreeRTOS task at CONTROL_HZ
//        │  1. Read targets atomically
//        │  2. Slew current powers toward targets (rate limiter)
//        │  3. Write PWM + direction to H-bridge
//
// Smooth motion
// ─────────────
// The rate limiter clamps how much current power may change per update tick.
// At CONTROL_HZ = 50 Hz and MAX_DELTA_PER_TICK = 0.02:
//   - Full stop → full speed takes 0 → 1.0 / 0.02 = 50 ticks = 1.0 s
//   - Full speed → full stop takes the same
// These constants are tunable in the source.
//
// Direction → wheel power mapping
// ────────────────────────────────
// Given angle_deg ∈ [-180, 180]:
//   forward_component =  BASE_SPEED * cos(angle_rad)
//   turn_component    =  BASE_SPEED * sin(angle_rad)
//   left_power_target  = forward_component - turn_component
//   right_power_target = forward_component + turn_component
//
// Examples (BASE_SPEED = 0.6):
//   angle =   0°  →  L=+0.60  R=+0.60  (straight forward)
//   angle =  90°  →  L=-0.60  R=+0.60  (pivot right)
//   angle = -90°  →  L=+0.60  R=-0.60  (pivot left)
//   angle =  45°  →  L=+0.18  R=+0.77  (curve right) [values approximate]
//   angle = 180°  →  L=-0.60  R=-0.60  (straight backward)
// =============================================================================

#include <Arduino.h>
#include <math.h>
#include "Protocol.h"

struct WheelPins {
    uint8_t pwm;    // PWM output to H-bridge enable
    uint8_t dir;    // direction output (HIGH = forward)
    uint8_t enc_a;  // encoder channel A (interrupt-capable)
};

class WheelController {
public:
    // -------------------------------------------------------------------------
    // Tuning constants — adjust to match your hardware
    // -------------------------------------------------------------------------
    static constexpr float BASE_SPEED         = 0.6f;   // power at full-forward (0–1)
    static constexpr float MAX_DELTA_PER_TICK = 0.02f;  // max power change per update
    static constexpr int   CONTROL_HZ         = 50;     // update() call frequency

    // -------------------------------------------------------------------------
    // Construction
    // -------------------------------------------------------------------------
    WheelController(WheelPins left, WheelPins right,
                    float wheel_circumference_m  = 0.20f,
                    int   encoder_pulses_per_rev = 20);

    // Attach encoder interrupts and configure LEDC PWM channels.
    void begin();

    // -------------------------------------------------------------------------
    // Reference signal input — called from BT receive context
    // -------------------------------------------------------------------------

    // Accept a DirectionRefPayload received from the host computer.
    // Thread-safe (protected by mutex).
    void setDirectionRef(const Protocol::DirectionRefPayload& ref);

    // -------------------------------------------------------------------------
    // Control loop — call from a dedicated FreeRTOS task at CONTROL_HZ
    // -------------------------------------------------------------------------

    // 1. Read current direction reference (mutex-protected).
    // 2. Compute desired wheel powers from angle/stop.
    // 3. Slew actual powers toward desired powers (rate limiter).
    // 4. Write PWM to H-bridge.
    void update();

    // Immediate hardware stop — bypasses the rate limiter.
    // Use only for emergency / safety shutdowns.
    void emergencyStop();

    // -------------------------------------------------------------------------
    // Diagnostics (read-only, no mutex needed — floats are atomic on Xtensa)
    // -------------------------------------------------------------------------
    float currentLeftPower()  const { return _current_left;  }
    float currentRightPower() const { return _current_right; }

private:
    // -------------------------------------------------------------------------
    // Direction → target wheel power computation
    // -------------------------------------------------------------------------
    struct WheelTargets { float left; float right; };
    WheelTargets _computeTargets(float angle_deg, bool stop) const;

    // -------------------------------------------------------------------------
    // Low-level motor drive
    // -------------------------------------------------------------------------
    void _driveMotor(uint8_t pwm_channel, uint8_t dir_pin, float power);

    static float _clamp(float v, float lo, float hi) {
        return v < lo ? lo : (v > hi ? hi : v);
    }

    // -------------------------------------------------------------------------
    // Encoder ISRs
    // -------------------------------------------------------------------------
    static void IRAM_ATTR _leftEncoderISR();
    static void IRAM_ATTR _rightEncoderISR();
    static WheelController* _instance;   // singleton pointer for ISR access

    // -------------------------------------------------------------------------
    // Hardware configuration
    // -------------------------------------------------------------------------
    WheelPins _left;
    WheelPins _right;

    float _wheel_circumference_m;
    int   _pulses_per_rev;

    static constexpr uint8_t LEFT_PWM_CHANNEL  = 2;
    static constexpr uint8_t RIGHT_PWM_CHANNEL = 3;

    // -------------------------------------------------------------------------
    // State — direction reference (written by BT task, read by control task)
    // -------------------------------------------------------------------------
    SemaphoreHandle_t _ref_mutex;
    float   _ref_angle_deg { 0.0f };
    uint8_t _ref_stop      { 1 };    // start stopped until first command arrives

    // -------------------------------------------------------------------------
    // State — current (smoothed) wheel powers (only written by control task)
    // -------------------------------------------------------------------------
    float _current_left  { 0.0f };
    float _current_right { 0.0f };

    // -------------------------------------------------------------------------
    // Encoder counters (written by ISR)
    // -------------------------------------------------------------------------
    volatile int32_t _left_pulses  { 0 };
    volatile int32_t _right_pulses { 0 };
};
