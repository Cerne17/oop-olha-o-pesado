#include "WheelController.h"

WheelController* WheelController::_instance = nullptr;

// ---------------------------------------------------------------------------
WheelController::WheelController(WheelPins left, WheelPins right,
                                  float wheel_circumference_m,
                                  int   encoder_pulses_per_rev)
    : _left(left), _right(right),
      _wheel_circumference_m(wheel_circumference_m),
      _pulses_per_rev(encoder_pulses_per_rev)
{
    _instance  = this;
    _ref_mutex = xSemaphoreCreateMutex();
}

// ---------------------------------------------------------------------------
void WheelController::begin() {
    // Direction pins
    pinMode(_left.dir,  OUTPUT);
    pinMode(_right.dir, OUTPUT);

    // PWM via LEDC (20 kHz, 8-bit resolution)
    ledcSetup(LEFT_PWM_CHANNEL,  20000, 8);
    ledcSetup(RIGHT_PWM_CHANNEL, 20000, 8);
    ledcAttachPin(_left.pwm,  LEFT_PWM_CHANNEL);
    ledcAttachPin(_right.pwm, RIGHT_PWM_CHANNEL);

    // Encoders
    pinMode(_left.enc_a,  INPUT_PULLUP);
    pinMode(_right.enc_a, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(_left.enc_a),  _leftEncoderISR,  RISING);
    attachInterrupt(digitalPinToInterrupt(_right.enc_a), _rightEncoderISR, RISING);

    // Make sure motors are off at startup
    _driveMotor(LEFT_PWM_CHANNEL,  _left.dir,  0.0f);
    _driveMotor(RIGHT_PWM_CHANNEL, _right.dir, 0.0f);

    Serial.println("[WHEEL] WheelController initialised (smooth-motion mode)");
}

// ---------------------------------------------------------------------------
// Reference input — called from the BT receive task
// ---------------------------------------------------------------------------
void WheelController::setDirectionRef(const Protocol::DirectionRefPayload& ref) {
    if (xSemaphoreTake(_ref_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
        _ref_angle_deg = ref.angle_deg;
        _ref_stop      = ref.stop;
        xSemaphoreGive(_ref_mutex);
    }
}

// ---------------------------------------------------------------------------
// Direction → target wheel power computation
// ---------------------------------------------------------------------------
WheelController::WheelTargets
WheelController::_computeTargets(float angle_deg, bool stop) const {
    if (stop) return { 0.0f, 0.0f };

    float angle_rad = angle_deg * (M_PI / 180.0f);

    // Decompose the angle into a forward and a turning component.
    // Both are scaled by BASE_SPEED so the robot moves at a consistent pace.
    float forward = BASE_SPEED * cosf(angle_rad);
    float turn    = BASE_SPEED * sinf(angle_rad);

    float left  = _clamp(forward - turn, -1.0f, 1.0f);
    float right = _clamp(forward + turn, -1.0f, 1.0f);

    return { left, right };
}

// ---------------------------------------------------------------------------
// Control loop — runs at CONTROL_HZ (50 Hz) from RobotComm's control task
// ---------------------------------------------------------------------------
void WheelController::update() {
    // --- 1. Read direction reference atomically ---
    float   angle_deg;
    uint8_t stop_flag;

    if (xSemaphoreTake(_ref_mutex, 0) == pdTRUE) {
        angle_deg = _ref_angle_deg;
        stop_flag = _ref_stop;
        xSemaphoreGive(_ref_mutex);
    } else {
        // Could not acquire mutex this tick — keep previous targets
        angle_deg = _ref_angle_deg;
        stop_flag = _ref_stop;
    }

    // --- 2. Compute desired (target) wheel powers ---
    WheelTargets target = _computeTargets(angle_deg, stop_flag != 0);

    // --- 3. Rate limiter — slew current power toward target ---
    //
    // This is the key anti-abruptness mechanism.  No matter how fast the
    // reference signal changes, the actual motor power can only change by
    // MAX_DELTA_PER_TICK per update cycle.
    auto slew = [](float current, float target) -> float {
        float delta = target - current;
        if (delta >  MAX_DELTA_PER_TICK) delta =  MAX_DELTA_PER_TICK;
        if (delta < -MAX_DELTA_PER_TICK) delta = -MAX_DELTA_PER_TICK;
        return current + delta;
    };

    _current_left  = slew(_current_left,  target.left);
    _current_right = slew(_current_right, target.right);

    // --- 4. Apply to hardware ---
    _driveMotor(LEFT_PWM_CHANNEL,  _left.dir,  _current_left);
    _driveMotor(RIGHT_PWM_CHANNEL, _right.dir, _current_right);
}

// ---------------------------------------------------------------------------
// Emergency stop — immediate, bypasses rate limiter
// ---------------------------------------------------------------------------
void WheelController::emergencyStop() {
    _current_left  = 0.0f;
    _current_right = 0.0f;
    _driveMotor(LEFT_PWM_CHANNEL,  _left.dir,  0.0f);
    _driveMotor(RIGHT_PWM_CHANNEL, _right.dir, 0.0f);

    if (xSemaphoreTake(_ref_mutex, portMAX_DELAY) == pdTRUE) {
        _ref_stop = 1;
        xSemaphoreGive(_ref_mutex);
    }
}

// ---------------------------------------------------------------------------
// Low-level motor write
// ---------------------------------------------------------------------------
void WheelController::_driveMotor(uint8_t channel, uint8_t dir_pin, float power) {
    power = _clamp(power, -1.0f, 1.0f);
    bool forward = (power >= 0.0f);
    uint8_t duty = static_cast<uint8_t>(fabsf(power) * 255.0f);

    digitalWrite(dir_pin, forward ? HIGH : LOW);
    ledcWrite(channel, duty);
}

// ---------------------------------------------------------------------------
// Encoder ISRs
// ---------------------------------------------------------------------------
void IRAM_ATTR WheelController::_leftEncoderISR() {
    if (_instance) _instance->_left_pulses++;
}

void IRAM_ATTR WheelController::_rightEncoderISR() {
    if (_instance) _instance->_right_pulses++;
}
