#include "CameraModule.h"

CameraModule::CameraModule(framesize_t resolution, int quality)
    : _resolution(resolution), _quality(quality)
{}

camera_config_t CameraModule::_buildConfig() const {
    camera_config_t cfg;

    cfg.pin_pwdn      = AiThinkerPins::PWDN;
    cfg.pin_reset     = AiThinkerPins::RESET;
    cfg.pin_xclk      = AiThinkerPins::XCLK;
    cfg.pin_sscb_sda  = AiThinkerPins::SIOD;
    cfg.pin_sscb_scl  = AiThinkerPins::SIOC;
    cfg.pin_d7        = AiThinkerPins::Y9;
    cfg.pin_d6        = AiThinkerPins::Y8;
    cfg.pin_d5        = AiThinkerPins::Y7;
    cfg.pin_d4        = AiThinkerPins::Y6;
    cfg.pin_d3        = AiThinkerPins::Y5;
    cfg.pin_d2        = AiThinkerPins::Y4;
    cfg.pin_d1        = AiThinkerPins::Y3;
    cfg.pin_d0        = AiThinkerPins::Y2;
    cfg.pin_vsync     = AiThinkerPins::VSYNC;
    cfg.pin_href      = AiThinkerPins::HREF;
    cfg.pin_pclk      = AiThinkerPins::PCLK;

    cfg.xclk_freq_hz  = 20000000;           // 20 MHz
    cfg.ledc_timer    = LEDC_TIMER_0;
    cfg.ledc_channel  = LEDC_CHANNEL_0;

    cfg.pixel_format  = PIXFORMAT_JPEG;     // always send compressed JPEG
    cfg.frame_size    = _resolution;
    cfg.jpeg_quality  = _quality;
    cfg.fb_count      = 2;                  // double-buffer for higher FPS

    // Use PSRAM when available (AI Thinker board has 4 MB PSRAM)
    cfg.fb_location   = CAMERA_FB_IN_PSRAM;
    cfg.grab_mode     = CAMERA_GRAB_WHEN_EMPTY;

    return cfg;
}

bool CameraModule::begin() {
    camera_config_t cfg = _buildConfig();
    esp_err_t err = esp_camera_init(&cfg);
    if (err != ESP_OK) {
        Serial.printf("[CAM] esp_camera_init failed: 0x%x\n", err);
        _ready = false;
        return false;
    }

    // Fine-tune sensor registers for better image quality
    sensor_t* s = esp_camera_sensor_get();
    if (s) {
        s->set_brightness(s, 0);
        s->set_contrast(s, 0);
        s->set_saturation(s, 0);
        s->set_whitebal(s, 1);   // auto white balance
        s->set_gain_ctrl(s, 1);  // auto gain
        s->set_exposure_ctrl(s, 1);
    }

    _ready = true;
    Serial.println("[CAM] Camera initialised");
    return true;
}

camera_fb_t* CameraModule::capture() {
    if (!_ready) return nullptr;
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("[CAM] Capture failed (fb_get returned null)");
    }
    return fb;
}

void CameraModule::releaseFrame(camera_fb_t* fb) {
    if (fb) esp_camera_fb_return(fb);
}

bool CameraModule::setResolution(framesize_t resolution) {
    _resolution = resolution;
    sensor_t* s = esp_camera_sensor_get();
    if (!s) return false;
    return s->set_framesize(s, resolution) == 0;
}

bool CameraModule::setQuality(int quality) {
    _quality = quality;
    sensor_t* s = esp_camera_sensor_get();
    if (!s) return false;
    return s->set_quality(s, quality) == 0;
}
