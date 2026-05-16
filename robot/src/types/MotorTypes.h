#pragma once
// =============================================================================
// robot/src/types/MotorTypes.h — hardware-adjacent structs for motor control.
//
// Shared between robot/control/ (WheelController) and robot/communication/
// (RobotComm) so neither module needs to include the other's header.
// See SPEC.md §10.2 and §12.
// =============================================================================

#include <stdint.h>

// Pins wired to one side of the L298N H-bridge
struct WheelPins {
    uint8_t en;    // ENA/ENB  — PWM speed control
    uint8_t dir;   // IN1/IN3  — HIGH = forward
    uint8_t esq;   // IN2/IN4  — LOW  = forward (complement of dir)
};

// Normalised per-wheel power target or reading
struct WheelSpeeds {
    float left;    // [-1.0, 1.0]
    float right;   // [-1.0, 1.0]
};
