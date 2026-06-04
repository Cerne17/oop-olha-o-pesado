#pragma once
// =============================================================================
// robot/src/control/WheelController.h — differential-drive motor controller.
//
// Accepts a ControlRefPayload (angle_deg + speed_ref) from the communication
// layer, measures actual per-wheel velocity via optic encoders, and drives
// each wheel with an independent PID controller (position form, FF disabled).
//
// Wheel power formula (SPEC.md §4.2):
//   rad   = radians(angle_deg)
//   fwd   = speed_ref * cos(rad)
//   turn  = speed_ref * sin(rad)
//   left  = clamp(fwd - turn, -1, 1)
//   right = clamp(fwd + turn, -1, 1)
//
// Encoder velocity (normalized, per update() tick):
//   y = dir_sign * clamp(Δticks / ticks_per_period_max, 0, 1)
//   dir_sign derived from H-bridge direction pins set in previous tick.
// =============================================================================

#include <Arduino.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "../types/Protocol.h"
#include "../types/MotorTypes.h"
#include "PIDController.h"

class WheelController {
public:
    // -------------------------------------------------------------------------
    // Tuning constants
    // -------------------------------------------------------------------------
    static constexpr int CONTROL_HZ = 50;  // update() call frequency

    // -------------------------------------------------------------------------
    // Construction
    // -------------------------------------------------------------------------

    // enc_left_pin / enc_right_pin  — GPIO pins wired to encoder signal outputs.
    // ticks_per_period_max          — ticks counted in one 20 ms period at full
    //                                  speed on flat ground; calibrate empirically.
    // kp / ki / kd                  — PID gains, same for both wheels (tune in
    //                                  main.cpp; both wheels share the same plant).
    WheelController(WheelPins left, WheelPins right,
                    uint8_t enc_left_pin, uint8_t enc_right_pin,
                    float ticks_per_period_max,
                    float kp, float ki, float kd);

    // Configure LEDC PWM channels, GPIO directions, and attach encoder ISRs.
    void begin();

    // -------------------------------------------------------------------------
    // Reference input — called from UDP receive task (any task)
    // -------------------------------------------------------------------------

    // Set the desired motion reference. Thread-safe (mutex-protected).
    void setRef(const Protocol::ControlRefPayload& ref);

    // -------------------------------------------------------------------------
    // Control loop — call from a dedicated FreeRTOS task at CONTROL_HZ
    // -------------------------------------------------------------------------

    // 1. Read current reference atomically.
    // 2. Compute target wheel speeds (_computeTargets).
    // 3. Measure actual wheel velocities from encoders.
    // 4. Run per-wheel PID.
    // 5. Write PWM to H-bridge.
    void update();

    // Immediate hardware stop — resets PID state and zeroes PWM.
    // Use only for emergency / safety shutdowns.
    void emergencyStop();

    // Diagnostics — returns last measured normalized velocity per wheel.
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

    uint8_t _enc_left_pin;
    uint8_t _enc_right_pin;

    static constexpr uint8_t  LEFT_CHANNEL  = 2;
    static constexpr uint8_t  RIGHT_CHANNEL = 3;
    static constexpr uint32_t PWM_FREQ      = 5000;  // Hz
    static constexpr uint8_t  PWM_RES_BITS  = 8;     // 0–255

    // -------------------------------------------------------------------------
    // PID controllers (one per wheel)
    // -------------------------------------------------------------------------
    float         _ticks_per_period_max;
    PIDController _pid_left;
    PIDController _pid_right;

    // -------------------------------------------------------------------------
    // State — reference (written by UDP task, read by control task)
    // -------------------------------------------------------------------------
    SemaphoreHandle_t           _ref_mutex;
    Protocol::ControlRefPayload _ref {};

    // -------------------------------------------------------------------------
    // State — last measured velocities (written by control task only)
    // -------------------------------------------------------------------------
    float _current_left  { 0.0f };
    float _current_right { 0.0f };
};
