#include <Arduino.h>

// Pinos do H-bridge usados no WheelController
static constexpr uint8_t PIN_LEFT_EN    = 13;
static constexpr uint8_t PIN_LEFT_IN1  = 12;
static constexpr uint8_t PIN_LEFT_IN2  = 14;
static constexpr uint8_t PIN_RIGHT_EN   = 25;
static constexpr uint8_t PIN_RIGHT_IN1 = 26;
static constexpr uint8_t PIN_RIGHT_IN2 = 27;

void setup_() {
  Serial.begin(115200);
  delay(500);
  Serial.println("=== H-bridge pin test ===");

  pinMode(PIN_LEFT_EN, OUTPUT);
  pinMode(PIN_LEFT_IN1, OUTPUT);
  pinMode(PIN_LEFT_IN2, OUTPUT);
  pinMode(PIN_RIGHT_EN, OUTPUT);
  pinMode(PIN_RIGHT_IN1, OUTPUT);
  pinMode(PIN_RIGHT_IN2, OUTPUT);

  digitalWrite(PIN_LEFT_EN, LOW);
  digitalWrite(PIN_LEFT_IN1, LOW);
  digitalWrite(PIN_LEFT_IN2, LOW);
  digitalWrite(PIN_RIGHT_EN, LOW);
  digitalWrite(PIN_RIGHT_IN1, LOW);
  digitalWrite(PIN_RIGHT_IN2, LOW);
}

void loop_() {


  Serial.println("Stop");
  digitalWrite(PIN_LEFT_EN, LOW);
  digitalWrite(PIN_RIGHT_EN, LOW);
  delay(2000);
}
