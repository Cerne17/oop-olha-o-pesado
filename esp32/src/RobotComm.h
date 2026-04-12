#pragma once
// =============================================================================
// RobotComm.h — Top-level orchestrator.
//
// Responsibilities:
//   - Drives BluetoothComm.poll() continuously in a dedicated FreeRTOS task.
//   - Runs the camera capture + transmission loop in a second task.
//   - Runs the telemetry transmission loop in a third task.
//   - Wires up the WHEEL_CONTROL callback so received commands are applied
//     to WheelController immediately.
//   - Sends periodic heartbeats to detect connection loss.
// =============================================================================

#include <Arduino.h>
#include "BluetoothComm.h"
#include "CameraModule.h"
#include "WheelController.h"

struct RobotCommConfig {
    const char* bt_device_name   = "RobotESP32";

    // Camera
    framesize_t camera_resolution = FRAMESIZE_QVGA;   // 320x240
    int         camera_quality    = 15;               // JPEG quality (lower = bigger)

    // Wheel hardware pins — adapt to your wiring
    WheelPins   left_wheel        = { .pwm = 14, .dir = 12, .enc_a = 13 };
    WheelPins   right_wheel       = { .pwm = 15, .dir = 2,  .enc_a = 4  };

    // Tuning
    float wheelbase_m            = 0.20f;
    float wheel_circumference_m  = 0.20f;
    int   encoder_pulses_per_rev = 20;

    // Task timing
    uint32_t telemetry_interval_ms  = 100;   // 10 Hz
    uint32_t heartbeat_interval_ms  = 1000;  // 1 Hz
    uint32_t camera_interval_ms     = 100;   // ~10 FPS (adjust for bandwidth)
};

class RobotComm {
public:
    explicit RobotComm(const RobotCommConfig& cfg = RobotCommConfig{});

    // Initialise all subsystems and spawn FreeRTOS tasks.
    // Returns false if any subsystem fails to start.
    bool begin();

    // Read-only access to the underlying modules (for diagnostics/extension).
    BluetoothComm&    bluetooth()    { return _bt; }
    CameraModule&     camera()       { return _cam; }
    WheelController&  wheels()       { return _wheels; }

private:
    // FreeRTOS task functions (static because xTaskCreate needs a plain pointer)
    static void _btTask(void* pvParameters);        // poll BT + heartbeat
    static void _cameraTask(void* pvParameters);    // capture + stream frames
    static void _telemetryTask(void* pvParameters); // periodic telemetry TX

    void _onWheelControl(const uint8_t* payload, size_t len);

    RobotCommConfig  _cfg;
    BluetoothComm    _bt;
    CameraModule     _cam;
    WheelController  _wheels;

    TaskHandle_t _bt_task_handle       { nullptr };
    TaskHandle_t _cam_task_handle      { nullptr };
    TaskHandle_t _telemetry_task_handle{ nullptr };
};
