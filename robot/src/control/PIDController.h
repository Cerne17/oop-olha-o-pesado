#pragma once
#include <math.h>

class PIDController {
public:
    PIDController(float kp, float ki, float kd, float dt);

    // r = normalized reference [-1,1], y = normalized measured velocity [-1,1]
    // Returns normalized PWM output [-1,1]
    float compute(float r, float y);

    void reset();

private:
    static float _clamp(float v, float lo, float hi);

    float _kp, _ki, _kd, _dt;
    float _integral  { 0.0f };
    float _prev_error{ 0.0f };
};
