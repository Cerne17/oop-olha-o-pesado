#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"
#include <lwip/sockets.h>
#include "credentials.h"

// AI Thinker ESP32-CAM pin map
#define PWDN_GPIO_NUM   32
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM    0
#define SIOD_GPIO_NUM   26
#define SIOC_GPIO_NUM   27
#define Y9_GPIO_NUM     35
#define Y8_GPIO_NUM     34
#define Y7_GPIO_NUM     39
#define Y6_GPIO_NUM     36
#define Y5_GPIO_NUM     21
#define Y4_GPIO_NUM     19
#define Y3_GPIO_NUM     18
#define Y2_GPIO_NUM      5
#define VSYNC_GPIO_NUM  25
#define HREF_GPIO_NUM   23
#define PCLK_GPIO_NUM   22

static constexpr uint16_t STREAM_PORT = 81;

httpd_handle_t stream_httpd = NULL;

static esp_err_t stream_handler(httpd_req_t* req) {
    camera_fb_t* fb  = NULL;
    esp_err_t    res = ESP_OK;
    size_t       jpg_len = 0;
    uint8_t*     jpg_buf = NULL;
    char         part_buf[128];

    int fd      = httpd_req_to_sockfd(req);
    int nodelay = 1;
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &nodelay, sizeof(nodelay));

    res = httpd_resp_set_type(req,
        "multipart/x-mixed-replace;boundary=123456789000000000000987654321");
    if (res != ESP_OK) return res;

    while (true) {
        fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("[CAM] Frame capture failed");
            res = ESP_FAIL;
        } else {
            if (fb->format != PIXFORMAT_JPEG) {
                bool ok = frame2jpg(fb, 80, &jpg_buf, &jpg_len);
                esp_camera_fb_return(fb);
                fb = NULL;
                if (!ok) { res = ESP_FAIL; }
            } else {
                jpg_len = fb->len;
                jpg_buf = fb->buf;
            }
        }

        if (res == ESP_OK) {
            size_t hlen = snprintf(part_buf, sizeof(part_buf),
                "\r\n--123456789000000000000987654321\r\n"
                "Content-Type: image/jpeg\r\n"
                "Content-Length: %u\r\n\r\n", jpg_len);
            res = httpd_resp_send_chunk(req, part_buf, hlen);
        }
        if (res == ESP_OK)
            res = httpd_resp_send_chunk(req, (const char*)jpg_buf, jpg_len);

        if (fb) {
            esp_camera_fb_return(fb);
            fb = NULL;
        } else if (jpg_buf) {
            free(jpg_buf);
            jpg_buf = NULL;
        }

        if (res != ESP_OK) break;
    }
    return res;
}

static void startCameraServer() {
    httpd_config_t cfg    = HTTPD_DEFAULT_CONFIG();
    cfg.server_port       = STREAM_PORT;
    cfg.ctrl_port         = 32768;
    cfg.stack_size        = 8192;
    cfg.task_priority     = tskIDLE_PRIORITY + 5;
    cfg.core_id           = 1;
    cfg.max_open_sockets  = 2;
    cfg.recv_wait_timeout = 5;
    cfg.send_wait_timeout = 5;
    cfg.lru_purge_enable  = true;

    httpd_uri_t stream_uri = {
        .uri      = "/stream",
        .method   = HTTP_GET,
        .handler  = stream_handler,
        .user_ctx = NULL,
    };

    if (httpd_start(&stream_httpd, &cfg) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &stream_uri);
        Serial.printf("[CAM] Stream server on port %u\n", STREAM_PORT);
    }
}

void setup() {
    Serial.begin(115200);
    Serial.setDebugOutput(true);

    camera_config_t config = {};
    config.ledc_channel  = LEDC_CHANNEL_0;
    config.ledc_timer    = LEDC_TIMER_0;
    config.pin_d0        = Y2_GPIO_NUM;
    config.pin_d1        = Y3_GPIO_NUM;
    config.pin_d2        = Y4_GPIO_NUM;
    config.pin_d3        = Y5_GPIO_NUM;
    config.pin_d4        = Y6_GPIO_NUM;
    config.pin_d5        = Y7_GPIO_NUM;
    config.pin_d6        = Y8_GPIO_NUM;
    config.pin_d7        = Y9_GPIO_NUM;
    config.pin_xclk      = XCLK_GPIO_NUM;
    config.pin_pclk      = PCLK_GPIO_NUM;
    config.pin_vsync     = VSYNC_GPIO_NUM;
    config.pin_href      = HREF_GPIO_NUM;
    config.pin_sccb_sda  = SIOD_GPIO_NUM;
    config.pin_sccb_scl  = SIOC_GPIO_NUM;
    config.pin_pwdn      = PWDN_GPIO_NUM;
    config.pin_reset     = RESET_GPIO_NUM;
    config.xclk_freq_hz  = 6000000;
    config.pixel_format  = PIXFORMAT_JPEG;
    config.frame_size    = FRAMESIZE_VGA;
    config.jpeg_quality  = 8;
    config.grab_mode     = CAMERA_GRAB_LATEST;

    if (psramFound()) {
        config.fb_count    = 2;
        config.fb_location = CAMERA_FB_IN_PSRAM;
        Serial.println("[CAM] PSRAM found — frame buffers in PSRAM");
    } else {
        config.fb_count    = 1;
        config.fb_location = CAMERA_FB_IN_DRAM;
        Serial.println("[CAM] No PSRAM — frame buffer in DRAM");
    }

    if (esp_camera_init(&config) != ESP_OK) {
        Serial.println("[CAM] FATAL: camera init failed");
        return;
    }

    sensor_t* s = esp_camera_sensor_get();
    if (s) {
        s->set_framesize(s,     FRAMESIZE_VGA);
        s->set_quality(s,       8);
        s->set_gainceiling(s,   GAINCEILING_2X);
        s->set_whitebal(s,      1);
        s->set_awb_gain(s,      1);
        s->set_exposure_ctrl(s, 1);
        s->set_aec2(s,          0);
        s->set_dcw(s,           1);
    }

    WiFi.begin(WIFI_SSID, WIFI_PASS);
    WiFi.setSleep(false);
    Serial.print("[CAM] Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\n[CAM] WiFi IP: %s  RSSI: %d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());

    startCameraServer();
    Serial.printf("[CAM] Stream: http://%s:%u/stream\n",
                  WiFi.localIP().toString().c_str(), STREAM_PORT);
}

void loop() {
    delay(1000);
}
