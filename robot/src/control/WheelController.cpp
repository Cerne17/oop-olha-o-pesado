#include "WheelController.h"

// =============================================================================
// WheelController — implementation
// =============================================================================

WheelController::WheelController(WheelPins left, WheelPins right)
    : _left(left), _right(right)
{
    _ref_mutex = xSemaphoreCreateMutex();
}

void WheelController::begin() {
    // Configure LEDC PWM channels
    ledcSetup(LEFT_CHANNEL,  PWM_FREQ, PWM_RES_BITS);
    ledcSetup(RIGHT_CHANNEL, PWM_FREQ, PWM_RES_BITS);
    ledcAttachPin(_left.en,  LEFT_CHANNEL);
    ledcAttachPin(_right.en, RIGHT_CHANNEL);

    // Configure direction pins
    pinMode(_left.right,   OUTPUT);
    pinMode(_right.right,  OUTPUT);
    pinMode(_left.left,   OUTPUT);
    pinMode(_right.left,  OUTPUT);

    // Start stopped — coast state (IN1=LOW, IN2=LOW, ENA=0)
    ledcWrite(LEFT_CHANNEL,  0);
    ledcWrite(RIGHT_CHANNEL, 0);
    digitalWrite(_left.right,  LOW);
    digitalWrite(_right.right, LOW);
    digitalWrite(_left.left,  LOW);
    digitalWrite(_right.left, LOW);
}

// ---------------------------------------------------------------------------
// Reference input
// ---------------------------------------------------------------------------

void WheelController::setRef(const Protocol::ControlRefPayload& ref) {
    xSemaphoreTake(_ref_mutex, portMAX_DELAY);
    _ref = ref;
    xSemaphoreGive(_ref_mutex);
}

// ---------------------------------------------------------------------------
// Control loop (call at CONTROL_HZ)
// ---------------------------------------------------------------------------

void WheelController::update() {
    // 1. Read reference atomically
    Protocol::ControlRefPayload ref;
    xSemaphoreTake(_ref_mutex, portMAX_DELAY);
    ref = _ref;
    xSemaphoreGive(_ref_mutex);

    // 2. Compute targets
    WheelSpeeds targets = _computeTargets(ref.angle_deg, ref.speed_ref);

    // 3. Rate-limited slew — ramps each wheel toward its target
    _current_left  = _slew(_current_left,  targets.left);
    _current_right = _slew(_current_right, targets.right);

    // 4. Write to H-bridge
    _driveMotor(_left,  LEFT_CHANNEL,  _current_left);
    _driveMotor(_right, RIGHT_CHANNEL, _current_right);
}

void WheelController::emergencyStop() {
    _current_left  = 0.0f;
    _current_right = 0.0f;

    // Drive H-bridge to coast state: EN=0, IN1=LOW, IN2=LOW.
    // Both direction pins must be cleared — leaving either HIGH with EN=0
    // is harmless electrically, but inconsistent with begin() and confusing.
    ledcWrite(LEFT_CHANNEL,  0);
    ledcWrite(RIGHT_CHANNEL, 0);
    digitalWrite(_left.right,  LOW);
    digitalWrite(_left.left,   LOW);
    digitalWrite(_right.right, LOW);
    digitalWrite(_right.left,  LOW);

    // Zero the stored reference so the next update() stays stopped.
    xSemaphoreTake(_ref_mutex, portMAX_DELAY);
    _ref = { 0.0f, 0.0f };
    xSemaphoreGive(_ref_mutex);
}

// ---------------------------------------------------------------------------
// Rate limiter
// ---------------------------------------------------------------------------

float WheelController::_slew(float current, float target) {
    float delta = target - current;
    if (delta >  MAX_DELTA_PER_TICK) delta =  MAX_DELTA_PER_TICK;
    if (delta < -MAX_DELTA_PER_TICK) delta = -MAX_DELTA_PER_TICK;
    return current + delta;
}

// ---------------------------------------------------------------------------
// Wheel power formula (SPEC.md §4.2)
// ---------------------------------------------------------------------------

WheelSpeeds WheelController::_computeTargets(float angle_deg,
                                              float speed_ref) const {
    float rad  = angle_deg * (float)M_PI / 180.0f;
    float fwd  = speed_ref * cosf(rad);
    float turn = speed_ref * sinf(rad);
    return {
        _clamp(fwd - turn, -1.0f, 1.0f),
        _clamp(fwd + turn, -1.0f, 1.0f),
    };
}

// ---------------------------------------------------------------------------
// Low-level motor drive
// ---------------------------------------------------------------------------

void WheelController::_driveMotor(const WheelPins& pins,
                                   uint8_t channel, float power) {
    if (power >= 0.0f) {
        digitalWrite(pins.right, HIGH);
        digitalWrite(pins.left, LOW);
        ledcWrite(channel, (uint32_t)(power * 255.0f));
    } else {
        digitalWrite(pins.right, LOW);
        digitalWrite(pins.left, HIGH);
        ledcWrite(channel, (uint32_t)(-power * 255.0f));
    }
}
