#include "communication/RobotComm.h"
#include "control/WheelController.h"
#include <Arduino.h>

// ---------------------------------------------------------------------------
// CONFIG — adapt pin numbers and UDP listen port to your setup
// ---------------------------------------------------------------------------
static constexpr uint16_t UDP_PORT = 5005;

// Indicator outputs
static constexpr uint8_t PIN_LED_YELLOW = 32;
static constexpr uint8_t PIN_LED_GREEN = 33;
static constexpr uint8_t PIN_LED_RED = 35;
static constexpr uint8_t PIN_BUZZER = 34;

// On-board LED (GPIO2 on this board) — toggled on every received command
// as a visual "RX activity" indicator. See RobotComm::_dispatchFrame().
static constexpr uint8_t PIN_LED_BUILTIN = 2;

// Left wheel  — ENA=GPIO14, IN1=GPIO12 (clockwise), IN2=GPIO13
// (counter-clockwise)
static constexpr WheelPins LEFT_WHEEL = {.en = 14, .right = 12, .left = 13};

// Right wheel — ENB=GPIO25, IN3=GPIO26  (clockwise), IN4=GPIO27
// (counter-clockwise)
static constexpr WheelPins RIGHT_WHEEL = {.en = 25, .right = 26, .left = 27, .invert = true};
// ---------------------------------------------------------------------------

static WheelController wheels(LEFT_WHEEL, RIGHT_WHEEL);
static RobotComm robot(wheels, UDP_PORT);

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("=== Robot ESP32 booting ===");

  pinMode(PIN_LED_YELLOW, OUTPUT);
  digitalWrite(PIN_LED_YELLOW, LOW);
  pinMode(PIN_LED_GREEN, OUTPUT);
  digitalWrite(PIN_LED_GREEN, LOW);
  pinMode(PIN_LED_RED, OUTPUT);
  digitalWrite(PIN_LED_RED, LOW);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  pinMode(PIN_LED_BUILTIN, OUTPUT);
  digitalWrite(PIN_LED_BUILTIN, LOW);

  wheels.begin();
  robot.begin();

  Serial.println("=== Ready ===");
}

void loop() {
  // All work is done inside FreeRTOS tasks spawned by robot.begin().
  vTaskDelay(pdMS_TO_TICKS(1000));
}
