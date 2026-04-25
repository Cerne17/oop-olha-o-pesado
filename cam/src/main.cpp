#include <Arduino.h>
#include "communication/CamComm.h"

// ---------------------------------------------------------------------------
// CONFIG — adapt Bluetooth name and frame rate to your deployment
// ---------------------------------------------------------------------------
static constexpr float TARGET_FPS  = 6.0f;
static const char*     BT_NAME     = "RobotCAM";
// ---------------------------------------------------------------------------

static CamComm cam(TARGET_FPS, BT_NAME);

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("=== CAM ESP32 booting ===");

    cam.begin();

    Serial.println("=== Ready ===");
}

void loop() {
    // All work is done inside FreeRTOS tasks spawned by cam.begin().
    vTaskDelay(pdMS_TO_TICKS(1000));
}
