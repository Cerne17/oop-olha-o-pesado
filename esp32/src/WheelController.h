#pragma once
// =============================================================================
// WheelController.h — PWM-based differential drive wheel controller.
//
// Each wheel is driven by an H-bridge that accepts:
//   - PWM pin   : motor speed  (0–255)
//   - DIR pin   : HIGH = forward, LOW = reverse
//
// Telemetry is gathered via encoder pulse counting (interrupt-driven).
// Call update() at a fixed rate (e.g., every 50 ms) to refresh RPM readings.
// =============================================================================

#include <Arduino.h>
#include "Protocol.h"

struct WheelPins {
    uint8_t pwm;    // PWM output to H-bridge enable
    uint8_t dir;    // direction pin
    uint8_t enc_a;  // encoder channel A (interrupt-capable pin)
};

class WheelController {
public:
    // wheelbase_m: distance between the two wheels in metres (used for speed calc)
    // wheel_circumference_m: metres per full wheel rotation
    // encoder_pulses_per_rev: encoder pulses per full wheel revolution
    WheelController(WheelPins left, WheelPins right,
                    float wheelbase_m            = 0.20f,
                    float wheel_circumference_m  = 0.20f,
                    int   encoder_pulses_per_rev = 20);

    // Attach interrupts and configure PWM channels.
    void begin();

    // Set wheel power in the range [-1.0, 1.0].
    //   +1.0 = full speed forward
    //   -1.0 = full speed reverse
    //    0.0 = stop
    void setLeftPower(float power);
    void setRightPower(float power);
    void setPower(float left, float right);  // convenience

    // Apply a WheelControlPayload received from the host.
    void applyControl(const Protocol::WheelControlPayload& cmd);

    // Refresh RPM and speed measurements. Call at a fixed interval.
    // interval_ms: actual elapsed time since the last call to update().
    void update(uint32_t interval_ms);

    // Read the latest telemetry. Call after update().
    Protocol::TelemetryPayload getTelemetry() const;

    // Emergency stop — cuts power to both wheels immediately.
    void stop();

private:
    WheelPins _left;
    WheelPins _right;

    float _wheelbase_m;
    float _wheel_circumference_m;
    int   _pulses_per_rev;

    // Encoder pulse counters — incremented in ISR.
    // volatile because they are written in interrupt context.
    volatile int32_t _left_pulses  { 0 };
    volatile int32_t _right_pulses { 0 };

    // Snapshot taken at the last update() call (for delta calculation).
    int32_t _prev_left_pulses  { 0 };
    int32_t _prev_right_pulses { 0 };

    // Latest computed values
    float _left_rpm   { 0.0f };
    float _right_rpm  { 0.0f };
    float _speed_mps  { 0.0f };

    // LEDC channels for PWM (ESP32-specific)
    static constexpr uint8_t LEFT_PWM_CHANNEL  = 2;
    static constexpr uint8_t RIGHT_PWM_CHANNEL = 3;
    static constexpr uint8_t PWM_FREQ_HZ       = 20;  // 20 kHz
    static constexpr uint8_t PWM_RESOLUTION    = 8;   // 8-bit (0–255)

    // Write motor command to hardware.
    void _driveMotor(uint8_t pwm_channel, uint8_t dir_pin, float power);

    // ISR friends — must be static to be used as raw function pointers.
    static void IRAM_ATTR _leftEncoderISR();
    static void IRAM_ATTR _rightEncoderISR();

    // Pointers to the single instance so the static ISRs can reach it.
    // (Only one WheelController instance is expected per firmware.)
    static WheelController* _instance;
};
