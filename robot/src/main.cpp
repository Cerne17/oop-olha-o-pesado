#include <Arduino.h>
#include "communication/RobotComm.h"
#include "control/WheelController.h"

// ---------------------------------------------------------------------------
// CONFIG — adapt pin numbers and UDP listen port to your setup
// ---------------------------------------------------------------------------
static constexpr uint16_t UDP_PORT = 5005;

// Indicator outputs
static constexpr uint8_t PIN_LED_YELLOW = 25;
static constexpr uint8_t PIN_LED_GREEN  = 26;
static constexpr uint8_t PIN_LED_RED    = 27;
static constexpr uint8_t PIN_BUZZER     = 33;

// Left wheel  — ENA=GPIO14, IN1=GPIO12 (clockwise), IN2=GPIO13 (counter-clockwise)
static constexpr WheelPins LEFT_WHEEL  = { .en = 14, .right = 12, .left = 13 };

// Right wheel — ENB=GPIO15, IN3=GPIO2  (clockwise), IN4=GPIO4  (counter-clockwise)
static constexpr WheelPins RIGHT_WHEEL = { .en = 15, .right =  2, .left =  4 };
// ---------------------------------------------------------------------------

static WheelController wheels(LEFT_WHEEL, RIGHT_WHEEL);
static RobotComm       robot(wheels, UDP_PORT);

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("=== Robot ESP32 booting ===");

    pinMode(PIN_LED_YELLOW, OUTPUT); digitalWrite(PIN_LED_YELLOW, LOW);
    pinMode(PIN_LED_GREEN,  OUTPUT); digitalWrite(PIN_LED_GREEN,  LOW);
    pinMode(PIN_LED_RED,    OUTPUT); digitalWrite(PIN_LED_RED,    LOW);
    pinMode(PIN_BUZZER,     OUTPUT); digitalWrite(PIN_BUZZER,     LOW);

    wheels.begin();
    robot.begin();

    Serial.println("=== Ready ===");
}

void loop() {
    // All work is done inside FreeRTOS tasks spawned by robot.begin().
    vTaskDelay(pdMS_TO_TICKS(1000));
}
