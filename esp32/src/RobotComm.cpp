#include "RobotComm.h"
#include <string.h>

// ---------------------------------------------------------------------------
RobotComm::RobotComm(const RobotCommConfig& cfg)
    : _cfg(cfg),
      _bt(cfg.bt_device_name),
      _cam(cfg.camera_resolution, cfg.camera_quality),
      _wheels(cfg.left_wheel, cfg.right_wheel,
              cfg.wheelbase_m,
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

    // Register the wheel-control message handler
    _bt.onMessage(Protocol::MsgType::WHEEL_CONTROL,
        [this](const uint8_t* payload, size_t len) {
            _onWheelControl(payload, len);
        });

    // Camera
    if (!_cam.begin()) {
        Serial.println("[ROBOT] Camera init failed");
        return false;
    }

    // Wheels
    _wheels.begin();

    // Spawn FreeRTOS tasks
    // BT task: high priority, small stack
    xTaskCreatePinnedToCore(_btTask,       "bt_task",       4096,  this, 5, &_bt_task_handle,        1);
    // Camera task: medium priority, large stack (JPEG encoding uses stack)
    xTaskCreatePinnedToCore(_cameraTask,   "cam_task",      8192,  this, 3, &_cam_task_handle,       0);
    // Telemetry task: low priority
    xTaskCreatePinnedToCore(_telemetryTask,"telem_task",    2048,  this, 2, &_telemetry_task_handle, 1);

    Serial.println("[ROBOT] All systems go");
    return true;
}

// ---------------------------------------------------------------------------
// Callback: received WHEEL_CONTROL frame from the host
// ---------------------------------------------------------------------------
void RobotComm::_onWheelControl(const uint8_t* payload, size_t len) {
    if (len < sizeof(Protocol::WheelControlPayload)) {
        Serial.println("[ROBOT] WheelControl payload too short");
        return;
    }
    Protocol::WheelControlPayload cmd;
    memcpy(&cmd, payload, sizeof(cmd));
    Serial.printf("[ROBOT] WheelControl: L=%.2f R=%.2f\n", cmd.left_power, cmd.right_power);
    _wheels.applyControl(cmd);
}

// ---------------------------------------------------------------------------
// FreeRTOS tasks
// ---------------------------------------------------------------------------
void RobotComm::_btTask(void* pv) {
    RobotComm* self = static_cast<RobotComm*>(pv);
    uint32_t last_heartbeat = millis();

    for (;;) {
        self->_bt.poll();

        // Send periodic heartbeat so the host can detect connection loss
        uint32_t now = millis();
        if (now - last_heartbeat >= self->_cfg.heartbeat_interval_ms) {
            if (self->_bt.isConnected()) {
                self->_bt.sendHeartbeat();
            } else {
                // Safety: stop wheels if link is lost
                self->_wheels.stop();
            }
            last_heartbeat = now;
        }

        vTaskDelay(pdMS_TO_TICKS(5));  // 5 ms polling interval
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

        // Chunk and transmit the JPEG
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

            // Small yield so the BT task can interleave ACKs / control frames
            taskYIELD();
        }

        self->_cam.releaseFrame(fb);
        frame_id++;
    }
}

void RobotComm::_telemetryTask(void* pv) {
    RobotComm* self = static_cast<RobotComm*>(pv);
    TickType_t last_wake = xTaskGetTickCount();

    for (;;) {
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(self->_cfg.telemetry_interval_ms));

        self->_wheels.update(self->_cfg.telemetry_interval_ms);

        if (self->_bt.isConnected()) {
            Protocol::TelemetryPayload t = self->_wheels.getTelemetry();
            self->_bt.sendTelemetry(t);
        }
    }
}
