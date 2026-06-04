#include "communication/RobotComm.h"
#include "control/WheelController.h"
#include <Arduino.h>

// ---------------------------------------------------------------------------
// CONFIG — adapt pin numbers and UDP listen port to your setup
// ---------------------------------------------------------------------------
static constexpr uint16_t UDP_PORT = 5005;

static constexpr uint8_t PIN_BUZZER = 4;

// Left wheel  — ENA=GPIO13, IN1=GPIO14 (clockwise), IN2=GPIO12
static constexpr WheelPins LEFT_WHEEL  = {.en = 13, .right = 14, .left = 12};

// Right wheel — ENB=GPIO25, IN3=GPIO26 (clockwise), IN4=GPIO27
static constexpr WheelPins RIGHT_WHEEL = {.en = 25, .right = 26, .left = 27, .invert = true};

static constexpr uint8_t ENC_LEFT_PIN  = 22;
static constexpr uint8_t ENC_RIGHT_PIN = 23;

// Ticks counted in one 20 ms period at full PWM on flat ground.
// Run with Kp=0/Ki=0/Kd=0 at full speed and Serial-print Δticks to calibrate.
static constexpr float TICKS_PER_PERIOD_MAX = 20.0f;

// PID gains — start conservative, increase Kp until tracking, then add Ki.
// Kd can stay near 0 unless encoder noise is filtered.
static constexpr float PID_KP = 0.5f;
static constexpr float PID_KI = 1.0f;
static constexpr float PID_KD = 0.01f;
// ---------------------------------------------------------------------------

static WheelController wheels(LEFT_WHEEL, RIGHT_WHEEL,
                               ENC_LEFT_PIN, ENC_RIGHT_PIN,
                               TICKS_PER_PERIOD_MAX,
                               PID_KP, PID_KI, PID_KD);
static RobotComm robot(wheels, UDP_PORT);

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("=== Robot ESP32 booting ===");

  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);

  wheels.begin();
  robot.begin();

  Serial.println("=== Ready ===");
}

void loop() {
  // All work is done inside FreeRTOS tasks spawned by robot.begin().
  vTaskDelay(pdMS_TO_TICKS(1000));
}
