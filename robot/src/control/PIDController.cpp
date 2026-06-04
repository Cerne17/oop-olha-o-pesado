#include "PIDController.h"

PIDController::PIDController(float kp, float ki, float kd, float dt)
    : _kp(kp), _ki(ki), _kd(kd), _dt(dt) {}

float PIDController::compute(float r, float y) {
    float e      = r - y;
    float p_term = _kp * e;
    float d_term = (_kd / _dt) * (e - _prev_error);

    // Probe output with current (old) integral to check saturation before update
    float u_probe = p_term + _integral + d_term;

    // Conditional anti-windup: freeze integral when saturated and error worsens saturation
    if (fabsf(u_probe) <= 1.0f || (e * _integral < 0.0f)) {
        _integral += _ki * _dt * e;
    }

    _prev_error = e;
    return _clamp(p_term + _integral + d_term, -1.0f, 1.0f);
}

void PIDController::reset() {
    _integral    = 0.0f;
    _prev_error  = 0.0f;
}

float PIDController::_clamp(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}
