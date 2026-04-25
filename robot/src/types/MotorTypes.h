#pragma once
// =============================================================================
// robot/src/types/MotorTypes.h — hardware-adjacent structs for motor control.
//
// Shared between robot/control/ (WheelController) and robot/communication/
// (RobotComm) so neither module needs to include the other's header.
// See SPEC.md §10.2 and §12.
// =============================================================================

#include <stdint.h>

// Pins wired to one side of the H-bridge
struct WheelPins {
    uint8_t pwm;   // PWM output to H-bridge enable pin
    uint8_t dir;   // direction pin (HIGH = forward)
};

// Normalised per-wheel power target or reading
struct WheelSpeeds {
    float left;    // [-1.0, 1.0]
    float right;   // [-1.0, 1.0]
};
