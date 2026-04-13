#pragma once
// =============================================================================
// RobotComm.h — Top-level orchestrator for the ESP32 robot.
//
// Spawns three FreeRTOS tasks:
//
//   bt_task      (core 1, priority 5) — polls BluetoothComm; dispatches
//                                       DIRECTION_REF to WheelController;
//                                       sends periodic heartbeats; calls
//                                       emergencyStop() on link loss.
//
//   camera_task  (core 0, priority 3) — captures JPEG frames, chunks and
//                                       streams them as IMAGE_CHUNK messages.
//
//   control_task (core 1, priority 4) — calls WheelController::update() at
//                                       WheelController::CONTROL_HZ (50 Hz)
//                                       to run the smooth-motion control loop.
// =============================================================================

#include <Arduino.h>
#include "BluetoothComm.h"
#include "CameraModule.h"
#include "WheelController.h"

struct RobotCommConfig {
    const char* bt_device_name   = "RobotESP32";

    // Camera
    framesize_t camera_resolution = FRAMESIZE_QVGA;   // 320×240
    int         camera_quality    = 15;

    // Wheel hardware pins — adapt to your wiring
    WheelPins left_wheel  = { .pwm = 14, .dir = 12, .enc_a = 13 };
    WheelPins right_wheel = { .pwm = 15, .dir =  2, .enc_a =  4 };

    float wheel_circumference_m  = 0.20f;
    int   encoder_pulses_per_rev = 20;

    // Timing
    uint32_t heartbeat_interval_ms = 1000;  // 1 Hz
    uint32_t camera_interval_ms    = 150;   // ~6-7 FPS
    // Control loop rate is fixed at WheelController::CONTROL_HZ (50 Hz)
};

class RobotComm {
public:
    explicit RobotComm(const RobotCommConfig& cfg = RobotCommConfig{});

    // Initialise all subsystems and spawn FreeRTOS tasks.
    bool begin();

    BluetoothComm&   bluetooth() { return _bt; }
    CameraModule&    camera()    { return _cam; }
    WheelController& wheels()    { return _wheels; }

private:
    static void _btTask(void* pv);       // BT poll + heartbeat + safety stop
    static void _cameraTask(void* pv);   // JPEG capture + chunk TX
    static void _controlTask(void* pv);  // smooth-motion control at 50 Hz

    void _onDirectionRef(const uint8_t* payload, size_t len);

    RobotCommConfig  _cfg;
    BluetoothComm    _bt;
    CameraModule     _cam;
    WheelController  _wheels;

    TaskHandle_t _bt_task_handle      { nullptr };
    TaskHandle_t _cam_task_handle     { nullptr };
    TaskHandle_t _control_task_handle { nullptr };
};
