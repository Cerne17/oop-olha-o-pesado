#pragma once
// =============================================================================
// CameraModule.h — Wraps the ESP32-CAM (AI Thinker) camera.
//
// Captures JPEG frames on demand and exposes them as a raw buffer.
// The caller is responsible for releasing the frame with releaseFrame()
// after processing.
// =============================================================================

#include <Arduino.h>
#include "esp_camera.h"

// Pin map for the AI Thinker ESP32-CAM board
namespace AiThinkerPins {
constexpr int PWDN  = 32;
constexpr int RESET = -1;  // not connected
constexpr int XCLK  =  0;
constexpr int SIOD  = 26;
constexpr int SIOC  = 27;
constexpr int Y9    = 35;
constexpr int Y8    = 34;
constexpr int Y7    = 39;
constexpr int Y6    = 36;
constexpr int Y5    = 21;
constexpr int Y4    = 19;
constexpr int Y3    = 18;
constexpr int Y2    =  5;
constexpr int VSYNC = 25;
constexpr int HREF  = 23;
constexpr int PCLK  = 22;
} // namespace AiThinkerPins

class CameraModule {
public:
    // resolution: FRAMESIZE_QQVGA (160x120) … FRAMESIZE_SVGA (800x600)
    // quality:    0 (best) … 63 (worst JPEG compression)
    explicit CameraModule(framesize_t resolution = FRAMESIZE_QVGA,
                          int quality = 12);

    // Initialise the camera hardware. Returns false on failure.
    bool begin();

    // Capture a JPEG frame. Returns a pointer to the frame buffer on
    // success, nullptr on failure. The frame stays valid until you call
    // releaseFrame() or capture() again.
    camera_fb_t* capture();

    // Release the frame buffer back to the camera driver.
    void releaseFrame(camera_fb_t* fb);

    // Change resolution or quality at runtime (re-initialises the sensor).
    bool setResolution(framesize_t resolution);
    bool setQuality(int quality);

    // Accessors
    framesize_t resolution() const { return _resolution; }
    int         quality()    const { return _quality;    }
    bool        isReady()    const { return _ready;      }

private:
    framesize_t _resolution;
    int         _quality;
    bool        _ready { false };

    camera_config_t _buildConfig() const;
};
