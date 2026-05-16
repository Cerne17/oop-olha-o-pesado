#include <Arduino.h>
#include "communication/CamComm.h"

// ---------------------------------------------------------------------------
// CONFIG — adapt frame rate and UDP listen port to your deployment
// ---------------------------------------------------------------------------
static constexpr float    TARGET_FPS  = 6.0f;
static constexpr uint16_t UDP_PORT    = 5006;
// ---------------------------------------------------------------------------

static CamComm cam(TARGET_FPS, UDP_PORT);

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
