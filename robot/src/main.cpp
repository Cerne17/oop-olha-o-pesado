#include <Arduino.h>
#include "communication/RobotComm.h"
#include "control/WheelController.h"

// ---------------------------------------------------------------------------
// CONFIG — adapt pin numbers and Bluetooth name to your wiring
// ---------------------------------------------------------------------------
static const char* BT_NAME = "RobotESP32";

// Left wheel  — ENA=GPIO14, IN1=GPIO12, IN2=GPIO13
static constexpr WheelPins LEFT_WHEEL  = { .en = 14, .dir = 12, .esq = 13 };

// Right wheel — ENB=GPIO15, IN3=GPIO2,  IN4=GPIO4
static constexpr WheelPins RIGHT_WHEEL = { .en = 15, .dir =  2, .esq =  4 };
// ---------------------------------------------------------------------------

static WheelController wheels(LEFT_WHEEL, RIGHT_WHEEL);
static RobotComm       robot(wheels, BT_NAME);

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("=== Robot ESP32 booting ===");

    wheels.begin();
    robot.begin();

    Serial.println("=== Ready ===");
}

void loop() {
    // All work is done inside FreeRTOS tasks spawned by robot.begin().
    vTaskDelay(pdMS_TO_TICKS(1000));
}
