#include <Arduino.h>
#include "RobotComm.h"

// ---------------------------------------------------------------------------
// Customise the robot here — everything else is handled by RobotComm.
// ---------------------------------------------------------------------------
static RobotCommConfig buildConfig() {
    RobotCommConfig cfg;

    cfg.bt_device_name  = "RobotESP32";

    cfg.camera_resolution = FRAMESIZE_QVGA;   // 320x240 — good balance for BT bandwidth
    cfg.camera_quality    = 15;               // JPEG quality (10=high, 63=low)

    // Adjust these pin numbers to match your wiring:
    //   Left wheel H-bridge
    cfg.left_wheel  = { .pwm = 14, .dir = 12, .enc_a = 13 };
    //   Right wheel H-bridge
    cfg.right_wheel = { .pwm = 15, .dir =  2, .enc_a =  4 };

    cfg.wheelbase_m            = 0.20f;   // 20 cm between wheels
    cfg.wheel_circumference_m  = 0.20f;   // 20 cm circumference (~6.4 cm diameter)
    cfg.encoder_pulses_per_rev = 20;

    cfg.telemetry_interval_ms  = 100;   // 10 Hz telemetry
    cfg.heartbeat_interval_ms  = 1000;  // 1 Hz heartbeat
    cfg.camera_interval_ms     = 150;   // ~6-7 FPS (tune for available BT bandwidth)

    return cfg;
}

static RobotComm robot(buildConfig());

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("=== RobotESP32 booting ===");

    if (!robot.begin()) {
        Serial.println("FATAL: robot.begin() failed — halting");
        while (true) { delay(1000); }
    }
}

void loop() {
    // All real work happens inside FreeRTOS tasks spawned by robot.begin().
    // The Arduino loop task is kept alive but idle.
    vTaskDelay(pdMS_TO_TICKS(1000));
}
