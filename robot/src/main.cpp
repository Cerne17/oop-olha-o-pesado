#include <Arduino.h>
#include "communication/RobotComm.h"
#include "control/WheelController.h"

// ---------------------------------------------------------------------------
// CONFIG — adapt pin numbers and Bluetooth name to your wiring
// ---------------------------------------------------------------------------
static const char* BT_NAME = "RobotESP32";

// Left wheel H-bridge pins
static constexpr WheelPins LEFT_WHEEL  = { .pwm = 14, .dir = 12 };

// Right wheel H-bridge pins
static constexpr WheelPins RIGHT_WHEEL = { .pwm = 15, .dir =  2 };
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
