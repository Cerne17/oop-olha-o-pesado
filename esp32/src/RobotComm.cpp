#include "RobotComm.h"
#include <string.h>

// ---------------------------------------------------------------------------
RobotComm::RobotComm(const RobotCommConfig& cfg)
    : _cfg(cfg),
      _bt(cfg.bt_device_name),
      _cam(cfg.camera_resolution, cfg.camera_quality),
      _wheels(cfg.left_wheel, cfg.right_wheel,
              cfg.wheel_circumference_m,
              cfg.encoder_pulses_per_rev)
{}

// ---------------------------------------------------------------------------
bool RobotComm::begin() {
    // Bluetooth
    if (!_bt.begin()) {
        Serial.println("[ROBOT] BT init failed");
        return false;
    }

    // Register handler for the direction reference coming from the computer
    _bt.onMessage(Protocol::MsgType::DIRECTION_REF,
        [this](const uint8_t* payload, size_t len) {
            _onDirectionRef(payload, len);
        });

    // Camera
    if (!_cam.begin()) {
        Serial.println("[ROBOT] Camera init failed");
        return false;
    }

    // Wheels (starts stopped; control task drives update() at 50 Hz)
    _wheels.begin();

    // Spawn FreeRTOS tasks
    xTaskCreatePinnedToCore(_btTask,      "bt_task",      4096, this, 5,
                            &_bt_task_handle,      1);
    xTaskCreatePinnedToCore(_cameraTask,  "cam_task",     8192, this, 3,
                            &_cam_task_handle,     0);
    xTaskCreatePinnedToCore(_controlTask, "control_task", 2048, this, 4,
                            &_control_task_handle, 1);

    Serial.println("[ROBOT] All systems go");
    return true;
}

// ---------------------------------------------------------------------------
// DIRECTION_REF callback — runs in the BT task context
// ---------------------------------------------------------------------------
void RobotComm::_onDirectionRef(const uint8_t* payload, size_t len) {
    if (len < sizeof(Protocol::DirectionRefPayload)) {
        Serial.println("[ROBOT] DIRECTION_REF payload too short");
        return;
    }
    Protocol::DirectionRefPayload ref;
    memcpy(&ref, payload, sizeof(ref));

    Serial.printf("[ROBOT] DIRECTION_REF angle=%.1f stop=%d\n",
                  ref.angle_deg, ref.stop);
    _wheels.setDirectionRef(ref);
}

// ---------------------------------------------------------------------------
// FreeRTOS tasks
// ---------------------------------------------------------------------------
void RobotComm::_btTask(void* pv) {
    RobotComm* self = static_cast<RobotComm*>(pv);
    uint32_t last_heartbeat = millis();

    for (;;) {
        self->_bt.poll();

        uint32_t now = millis();
        if (now - last_heartbeat >= self->_cfg.heartbeat_interval_ms) {
            if (self->_bt.isConnected()) {
                self->_bt.sendHeartbeat();
            } else {
                // Safety: engage emergency stop if Bluetooth link is lost.
                // The control task will keep calling update() which will
                // smoothly ramp down to zero once the rate-limited current
                // reaches the target — but emergency stop cuts power immediately.
                self->_wheels.emergencyStop();
            }
            last_heartbeat = now;
        }

        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

void RobotComm::_cameraTask(void* pv) {
    RobotComm* self = static_cast<RobotComm*>(pv);
    uint16_t frame_id = 0;
    TickType_t last_wake = xTaskGetTickCount();

    for (;;) {
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(self->_cfg.camera_interval_ms));

        if (!self->_bt.isConnected()) continue;

        camera_fb_t* fb = self->_cam.capture();
        if (!fb) continue;

        const size_t chunk_data = Protocol::IMAGE_CHUNK_DATA_SIZE;
        size_t total_chunks = (fb->len + chunk_data - 1) / chunk_data;

        for (size_t i = 0; i < total_chunks; i++) {
            size_t offset     = i * chunk_data;
            size_t this_chunk = min(chunk_data, fb->len - offset);

            Protocol::ImageChunkHeader hdr {
                frame_id,
                static_cast<uint16_t>(i),
                static_cast<uint16_t>(total_chunks),
                static_cast<uint32_t>(fb->len)
            };

            if (!self->_bt.sendImageChunk(hdr, fb->buf + offset, this_chunk)) {
                Serial.printf("[CAM] Failed to send chunk %zu/%zu\n", i, total_chunks);
                break;
            }
            taskYIELD();
        }

        self->_cam.releaseFrame(fb);
        frame_id++;
    }
}

void RobotComm::_controlTask(void* pv) {
    RobotComm* self = static_cast<RobotComm*>(pv);
    const TickType_t period = pdMS_TO_TICKS(1000 / WheelController::CONTROL_HZ);
    TickType_t last_wake = xTaskGetTickCount();

    for (;;) {
        vTaskDelayUntil(&last_wake, period);
        // Drive the smooth-motion control loop.
        // update() reads the latest direction reference (set by _onDirectionRef),
        // applies the rate limiter, and writes PWM to the H-bridge.
        self->_wheels.update();
    }
}
