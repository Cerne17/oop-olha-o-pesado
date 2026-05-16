#pragma once
// =============================================================================
// robot/src/types/MotorTypes.h — hardware-adjacent structs for motor control.
//
// Shared between robot/control/ (WheelController) and robot/communication/
// (RobotComm) so neither module needs to include the other's header.
// See SPEC.md §10.2 and §12.
// =============================================================================

#include <stdint.h>

// GPIO pins wired to one side of an L298N (or equivalent) H-bridge.
//
// H-bridge truth table for a single motor channel:
//
//   en (PWM)  right (IN1)  left (IN2)  →  motor behaviour
//   --------  -----------  ----------     -----------------
//   > 0       HIGH         LOW         →  clockwise   (forward)
//   > 0       LOW          HIGH        →  counter-clockwise (reverse)
//   0         X            X           →  coast  (motor free-spins)
//   > 0       LOW          LOW         →  coast  (same as en=0)
//   > 0       HIGH         HIGH        →  brake  (avoid — short-circuits H-bridge)
//
// The firmware always drives `right` and `left` as logical complements.
// Never set both HIGH simultaneously.
struct WheelPins {
    uint8_t en;     // ENA/ENB — PWM pin; duty cycle sets speed (0=coast, 255=full)
    uint8_t right;  // IN1/IN3 — drive HIGH to spin the motor clockwise
    uint8_t left;   // IN2/IN4 — drive HIGH to spin the motor counter-clockwise
                    //           (always the complement of `right`)
};

// Normalised per-wheel power target or reading
struct WheelSpeeds {
    float left;    // [-1.0, 1.0]
    float right;   // [-1.0, 1.0]
};
