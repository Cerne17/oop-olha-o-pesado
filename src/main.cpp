#include "esp_camera.h"
#include <WiFi.h>

// ==========================================
// CONFIGURAÇÕES DA REDE WI-FI
// ==========================================
const char* ssid = "teste_oop";
const char* password = "teste_oop";

// ==========================================
// DEFINIÇÃO DOS PINOS (MODELO AI-THINKER)
// ==========================================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// Inicializa o servidor HTTP na porta 81 para o stream puro
#include "esp_http_server.h"
#include <lwip/sockets.h>
httpd_handle_t stream_httpd = NULL;

// Handler que processa o stream de vídeo em formato MJPEG
static esp_err_t stream_handler(httpd_req_t *req) {
    camera_fb_t * fb = NULL;
    esp_err_t res = ESP_OK;
    size_t _jpg_buf_len = 0;
    uint8_t * _jpg_buf = NULL;
    char part_buf[128];

    // Desativa Nagle no socket — manda chunks imediatamente em vez de bufferizar
    int fd = httpd_req_to_sockfd(req);
    int nodelay = 1;
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &nodelay, sizeof(nodelay));

    res = httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=123456789000000000000987654321");
    if (res != ESP_OK) return res;

    while (true) {
        fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("Falha ao capturar frame");
            res = ESP_FAIL;
        } else {
            if (fb->format != PIXFORMAT_JPEG) {
                bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
                esp_camera_fb_return(fb);
                fb = NULL;
                if (!jpeg_converted) {
                    Serial.println("Falha na conversao JPEG");
                    res = ESP_FAIL;
                }
            } else {
                _jpg_buf_len = fb->len;
                _jpg_buf = fb->buf;
            }
        }
        if (res == ESP_OK) {
            size_t hlen = snprintf(part_buf, sizeof(part_buf), "\r\n--123456789000000000000987654321\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", _jpg_buf_len);
            res = httpd_resp_send_chunk(req, part_buf, hlen);
        }
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
        }
        if (fb) {
            esp_camera_fb_return(fb);
            fb = NULL;
            _jpg_buf = NULL;
        } else if (_jpg_buf) {
            free(_jpg_buf);
            _jpg_buf = NULL;
        }
        if (res != ESP_OK) break;
    }
    return res;
}

// Inicializa o servidor web na porta 81
void startCameraServer() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 81;             // Porta do stream usada pelo Python
    config.ctrl_port = 32768;
    config.stack_size = 8192;            // default 4096 é apertado pra MJPEG
    config.task_priority = tskIDLE_PRIORITY + 5;
    config.core_id = 1;                  // Wi-Fi vive no core 0 — separa carga
    config.max_open_sockets = 2;
    config.recv_wait_timeout = 5;
    config.send_wait_timeout = 5;        // drop rápido de cliente lento
    config.lru_purge_enable = true;

    httpd_uri_t stream_uri = {
        .uri       = "/stream",
        .method    = HTTP_GET,
        .handler   = stream_handler,
        .user_ctx  = NULL
    };

    if (httpd_start(&stream_httpd, &config) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &stream_uri);
        Serial.println("Servidor de Stream inicializado na porta 81");
    }
}

void setup() {
    Serial.begin(115200);
    Serial.setDebugOutput(true);
    Serial.println();
    Serial.printf("CPU Freq: %d MHz\n", getCpuFrequencyMhz());
    Serial.printf("XTAL Freq: %d MHz\n", getXtalFrequencyMhz());
    Serial.printf("APB Freq: %d Hz\n", getApbFrequency());

    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sscb_sda = SIOD_GPIO_NUM;
    config.pin_sscb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 6000000;
    config.pixel_format = PIXFORMAT_JPEG;

    // Configurações de resolução ideais para processamento (VGA evita sobrecarga e latência no Wi-Fi)
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 8;          // 0-63 (números MAIORES = arquivo menor = mais rápido)
    config.fb_count = 2;               // Melhora a taxa de quadros (double buffering)
    config.grab_mode = CAMERA_GRAB_LATEST; // sempre serve o frame mais recente (menor latência)

    if (psramFound()) {
        Serial.println("PSRAM detectada — frame buffers em PSRAM");
        config.fb_location = CAMERA_FB_IN_PSRAM;
    } else {
        Serial.println("PSRAM NAO encontrada — caindo para DRAM com fb_count=1");
        config.fb_location = CAMERA_FB_IN_DRAM;
        config.fb_count = 1;
    }

    // Inicialização da Câmera
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("Falha na inicializacao da camera: 0x%x\n", err);
        return;
    }

    // Trava parâmetros do sensor para frames mais estáveis (sem "respiração" de AEC/AGC)
    sensor_t *s = esp_camera_sensor_get();
    if (s) {
        s->set_framesize(s, FRAMESIZE_VGA);
        s->set_quality(s, 8);
        s->set_brightness(s, 0);
        s->set_contrast(s, 0);
        s->set_saturation(s, 0);
        s->set_gainceiling(s, GAINCEILING_2X);
        s->set_whitebal(s, 1);
        s->set_awb_gain(s, 1);
        s->set_exposure_ctrl(s, 1);
        s->set_aec2(s, 0);
        s->set_dcw(s, 1);
    }

    // Conexão Wi-Fi
    WiFi.begin(ssid, password);
    WiFi.setSleep(false); // desativa modem-sleep para reduzir latência do stream
    Serial.print("Conectando ao Wi-Fi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWi-Fi Conectado!");
    Serial.printf("RSSI: %d dBm\n", WiFi.RSSI());

    // Inicia o servidor de stream
    startCameraServer();

    // Exibe o IP final no monitor serial
    Serial.print("Stream disponível em: http://");
    Serial.print(WiFi.localIP());
    Serial.println(":81/stream");
}

void loop() {
    // O loop fica livre, pois o http_server do ESP-IDF roda em background em uma tarefa separada (FreeRTOS)
    delay(1000);
}
