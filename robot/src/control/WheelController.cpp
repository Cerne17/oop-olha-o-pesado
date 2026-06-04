#include "WheelController.h"

// =============================================================================
// WheelController — implementation
// =============================================================================

// ---------------------------------------------------------------------------
// Encoder ISR state — file-scope so ISRs (static functions) can access them.
// IRAM_ATTR places variables in IRAM for fast ISR access on ESP32.
// ---------------------------------------------------------------------------
static volatile int32_t IRAM_ATTR s_enc_left_ticks  = 0;
static volatile int32_t IRAM_ATTR s_enc_right_ticks = 0;
static portMUX_TYPE s_enc_mux = portMUX_INITIALIZER_UNLOCKED;

static void IRAM_ATTR leftEncoderISR()  { s_enc_left_ticks++;  }
static void IRAM_ATTR rightEncoderISR() { s_enc_right_ticks++; }

// ---------------------------------------------------------------------------
// Construction
// ---------------------------------------------------------------------------

WheelController::WheelController(WheelPins left, WheelPins right,
                                  uint8_t enc_left_pin, uint8_t enc_right_pin,
                                  float ticks_per_period_max,
                                  float kp, float ki, float kd)
    : _left(left), _right(right),
      _enc_left_pin(enc_left_pin), _enc_right_pin(enc_right_pin),
      _ticks_per_period_max(ticks_per_period_max),
      _pid_left (kp, ki, kd, 1.0f / CONTROL_HZ),
      _pid_right(kp, ki, kd, 1.0f / CONTROL_HZ)
{
    _ref_mutex = xSemaphoreCreateMutex();
}

void WheelController::begin() {
    // LEDC PWM channels
    ledcSetup(LEFT_CHANNEL,  PWM_FREQ, PWM_RES_BITS);
    ledcSetup(RIGHT_CHANNEL, PWM_FREQ, PWM_RES_BITS);
    ledcAttachPin(_left.en,  LEFT_CHANNEL);
    ledcAttachPin(_right.en, RIGHT_CHANNEL);

    // Direction pins
    pinMode(_left.right,  OUTPUT);
    pinMode(_right.right, OUTPUT);
    pinMode(_left.left,   OUTPUT);
    pinMode(_right.left,  OUTPUT);

    // Start in coast state
    ledcWrite(LEFT_CHANNEL,  0);
    ledcWrite(RIGHT_CHANNEL, 0);
    digitalWrite(_left.right,  LOW);
    digitalWrite(_right.right, LOW);
    digitalWrite(_left.left,   LOW);
    digitalWrite(_right.left,  LOW);

    // Encoder pins — rising edge per slot
    pinMode(_enc_left_pin,  INPUT_PULLUP);
    pinMode(_enc_right_pin, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(_enc_left_pin),  leftEncoderISR,  RISING);
    attachInterrupt(digitalPinToInterrupt(_enc_right_pin), rightEncoderISR, RISING);
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

    // 3. Measure velocity — atomically read and reset tick counters
    int32_t left_ticks, right_ticks;
    portENTER_CRITICAL(&s_enc_mux);
    left_ticks  = s_enc_left_ticks;  s_enc_left_ticks  = 0;
    right_ticks = s_enc_right_ticks; s_enc_right_ticks = 0;
    portEXIT_CRITICAL(&s_enc_mux);

    // Derive direction sign from H-bridge pins set in the previous tick.
    // Invert flag corrects for physically mirrored wheels.
    float dir_left  = (digitalRead(_left.right)  ? 1.0f : -1.0f)
                    * (_left.invert  ? -1.0f : 1.0f);
    float dir_right = (digitalRead(_right.right) ? 1.0f : -1.0f)
                    * (_right.invert ? -1.0f : 1.0f);

    float y_left  = dir_left  * _clamp((float)left_ticks  / _ticks_per_period_max, 0.0f, 1.0f);
    float y_right = dir_right * _clamp((float)right_ticks / _ticks_per_period_max, 0.0f, 1.0f);

    // Store for diagnostics
    _current_left  = y_left;
    _current_right = y_right;

    // 4. PID
    float u_left  = _pid_left.compute(targets.left,  y_left);
    float u_right = _pid_right.compute(targets.right, y_right);

    // 5. Drive H-bridge
    _driveMotor(_left,  LEFT_CHANNEL,  u_left);
    _driveMotor(_right, RIGHT_CHANNEL, u_right);
}

void WheelController::emergencyStop() {
    // Zero H-bridge: EN=0, direction pins LOW (coast state)
    ledcWrite(LEFT_CHANNEL,  0);
    ledcWrite(RIGHT_CHANNEL, 0);
    digitalWrite(_left.right,  LOW);
    digitalWrite(_left.left,   LOW);
    digitalWrite(_right.right, LOW);
    digitalWrite(_right.left,  LOW);

    // Reset PID state so stale integral does not spike on resume
    _pid_left.reset();
    _pid_right.reset();

    _current_left  = 0.0f;
    _current_right = 0.0f;

    xSemaphoreTake(_ref_mutex, portMAX_DELAY);
    _ref = {};
    xSemaphoreGive(_ref_mutex);
}

// ---------------------------------------------------------------------------
// Wheel power formula (SPEC.md §4.2)
// ---------------------------------------------------------------------------

WheelSpeeds WheelController::_computeTargets(float angle_deg,
                                              float speed_ref) const {
    float rad  = - angle_deg * (float)M_PI / 180.0f;
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
    if (pins.invert) {
        power = -power;
    }

    if (power >= 0.0f) {
        digitalWrite(pins.right, HIGH);
        digitalWrite(pins.left,  LOW);
        ledcWrite(channel, (uint32_t)(power * 255.0f));
    } else {
        digitalWrite(pins.right, LOW);
        digitalWrite(pins.left,  HIGH);
        ledcWrite(channel, (uint32_t)(-power * 255.0f));
    }
}
