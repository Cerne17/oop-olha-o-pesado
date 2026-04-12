#include "WheelController.h"
#include <math.h>

WheelController* WheelController::_instance = nullptr;

// ---------------------------------------------------------------------------
WheelController::WheelController(WheelPins left, WheelPins right,
                                  float wheelbase_m,
                                  float wheel_circumference_m,
                                  int   encoder_pulses_per_rev)
    : _left(left), _right(right),
      _wheelbase_m(wheelbase_m),
      _wheel_circumference_m(wheel_circumference_m),
      _pulses_per_rev(encoder_pulses_per_rev)
{
    _instance = this;
}

// ---------------------------------------------------------------------------
void WheelController::begin() {
    // Direction pins
    pinMode(_left.dir,  OUTPUT);
    pinMode(_right.dir, OUTPUT);

    // PWM via LEDC
    ledcSetup(LEFT_PWM_CHANNEL,  20000, PWM_RESOLUTION);
    ledcSetup(RIGHT_PWM_CHANNEL, 20000, PWM_RESOLUTION);
    ledcAttachPin(_left.pwm,  LEFT_PWM_CHANNEL);
    ledcAttachPin(_right.pwm, RIGHT_PWM_CHANNEL);

    // Encoders
    pinMode(_left.enc_a,  INPUT_PULLUP);
    pinMode(_right.enc_a, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(_left.enc_a),  _leftEncoderISR,  RISING);
    attachInterrupt(digitalPinToInterrupt(_right.enc_a), _rightEncoderISR, RISING);

    stop();
    Serial.println("[WHEEL] WheelController initialised");
}

// ---------------------------------------------------------------------------
void WheelController::_driveMotor(uint8_t channel, uint8_t dir_pin, float power) {
    power = constrain(power, -1.0f, 1.0f);
    bool forward = (power >= 0.0f);
    uint8_t duty = static_cast<uint8_t>(fabsf(power) * 255.0f);

    digitalWrite(dir_pin, forward ? HIGH : LOW);
    ledcWrite(channel, duty);
}

void WheelController::setLeftPower(float power) {
    _driveMotor(LEFT_PWM_CHANNEL, _left.dir, power);
}

void WheelController::setRightPower(float power) {
    _driveMotor(RIGHT_PWM_CHANNEL, _right.dir, power);
}

void WheelController::setPower(float left, float right) {
    setLeftPower(left);
    setRightPower(right);
}

void WheelController::applyControl(const Protocol::WheelControlPayload& cmd) {
    setPower(cmd.left_power, cmd.right_power);
}

void WheelController::stop() {
    setPower(0.0f, 0.0f);
}

// ---------------------------------------------------------------------------
void WheelController::update(uint32_t interval_ms) {
    if (interval_ms == 0) return;

    // Atomic snapshot of interrupt-driven counters
    noInterrupts();
    int32_t lp = _left_pulses;
    int32_t rp = _right_pulses;
    interrupts();

    int32_t dl = lp - _prev_left_pulses;
    int32_t dr = rp - _prev_right_pulses;
    _prev_left_pulses  = lp;
    _prev_right_pulses = rp;

    float interval_min = interval_ms / 60000.0f;  // minutes

    _left_rpm  = (static_cast<float>(dl) / _pulses_per_rev) / interval_min;
    _right_rpm = (static_cast<float>(dr) / _pulses_per_rev) / interval_min;

    // Linear speed = average RPM * circumference / 60
    _speed_mps = ((_left_rpm + _right_rpm) / 2.0f)
                 * _wheel_circumference_m / 60.0f;
}

Protocol::TelemetryPayload WheelController::getTelemetry() const {
    return Protocol::TelemetryPayload {
        _left_rpm,
        _right_rpm,
        _speed_mps,
        static_cast<uint32_t>(millis())
    };
}

// ---------------------------------------------------------------------------
// ISR handlers
// ---------------------------------------------------------------------------
void IRAM_ATTR WheelController::_leftEncoderISR() {
    if (_instance) _instance->_left_pulses++;
}

void IRAM_ATTR WheelController::_rightEncoderISR() {
    if (_instance) _instance->_right_pulses++;
}
