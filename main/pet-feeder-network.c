#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_netif.h"
#include "esp_http_client.h"
#include "cJSON.h"
#include "driver/uart.h"
#include "driver/gpio.h"

#define ESP_WIFI_SSID      " Hotspot"
#define ESP_WIFI_PASS      "9876543210"
#define ESP_MAXIMUM_RETRY  5
#define SERVER_URL         "http://10.20.79.48:5000/tag"

#define UART_NUM           UART_NUM_1
#define UART_RX_PIN        9
#define UART_TX_PIN        10
#define UART_BUF_SIZE      (1024)

#define STEPPER_PIN_IN1    3
#define STEPPER_PIN_IN2    0
#define STEPPER_PIN_IN3    1
#define STEPPER_PIN_IN4    5
#define STEPPER_DELAY_MS   10
#define STEPS_PER_REVOLUTION 2048

void stepper_init(void);
void stepper_rotate(int num_steps, int direction);
void stepper_stop(void);
void stepper_set_step(int step);
void stepper_rotate_for_seconds(int duration_seconds);

static const char *TAG = "RFID";
static volatile bool motor_busy = false;
static EventGroupHandle_t s_wifi_event_group;
#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT      BIT1
static int s_retry_num = 0;

static void event_handler(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        if (s_retry_num < ESP_MAXIMUM_RETRY) {
            esp_wifi_connect();
            s_retry_num++;
        } else {
            xEventGroupSetBits(s_wifi_event_group, WIFI_FAIL_BIT);
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        ESP_LOGI(TAG, "IP: " IPSTR, IP2STR(&event->ip_info.ip));
        s_retry_num = 0;
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

void wifi_init_sta(void) {
    s_wifi_event_group = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    esp_event_handler_instance_t instance_any_id;
    esp_event_handler_instance_t instance_got_ip;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &event_handler, NULL, &instance_any_id));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &event_handler, NULL, &instance_got_ip));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = ESP_WIFI_SSID,
            .password = ESP_WIFI_PASS,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "WiFi init");

    EventBits_t bits = xEventGroupWaitBits(s_wifi_event_group,
            WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
            pdFALSE,
            pdFALSE,
            portMAX_DELAY);

    if (bits & WIFI_CONNECTED_BIT) {
        ESP_LOGI(TAG, "WiFi connected");
    } else {
        ESP_LOGI(TAG, "WiFi failed");
    }
}

void stepper_init(void) {
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << STEPPER_PIN_IN1) | (1ULL << STEPPER_PIN_IN2) |
                        (1ULL << STEPPER_PIN_IN3) | (1ULL << STEPPER_PIN_IN4),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&io_conf);

    gpio_set_level(STEPPER_PIN_IN1, 0);
    gpio_set_level(STEPPER_PIN_IN2, 0);
    gpio_set_level(STEPPER_PIN_IN3, 0);
    gpio_set_level(STEPPER_PIN_IN4, 0);

    ESP_LOGI(TAG, "Motor init");
}

void stepper_set_step(int step) {
    int steps[8][4] = {
        {1, 0, 0, 0},
        {1, 1, 0, 0},
        {0, 1, 0, 0},
        {0, 1, 1, 0},
        {0, 0, 1, 0},
        {0, 0, 1, 1},
        {0, 0, 0, 1},
        {1, 0, 0, 1},
    };

    step = step % 8;
    gpio_set_level(STEPPER_PIN_IN1, steps[step][0]);
    gpio_set_level(STEPPER_PIN_IN2, steps[step][1]);
    gpio_set_level(STEPPER_PIN_IN3, steps[step][2]);
    gpio_set_level(STEPPER_PIN_IN4, steps[step][3]);
}

void stepper_rotate(int num_steps, int direction) {
    static int current_step = 0;

    for (int i = 0; i < num_steps; i++) {
        current_step += direction;
        if (current_step < 0) {
            current_step = 7;
        }
        stepper_set_step(current_step);
        vTaskDelay(STEPPER_DELAY_MS / portTICK_PERIOD_MS);
    }
}

void stepper_stop(void) {
    gpio_set_level(STEPPER_PIN_IN1, 0);
    gpio_set_level(STEPPER_PIN_IN2, 0);
    gpio_set_level(STEPPER_PIN_IN3, 0);
    gpio_set_level(STEPPER_PIN_IN4, 0);
}

void stepper_rotate_for_seconds(int duration_seconds) {
    if (motor_busy) {
        ESP_LOGW(TAG, "Motor busy");
        return;
    }
    motor_busy = true;

    int steps_per_second = 1000 / STEPPER_DELAY_MS;
    int total_steps = duration_seconds * steps_per_second;

    ESP_LOGI(TAG, "Dispensing %ds", duration_seconds);
    stepper_rotate(total_steps, 1);
    stepper_stop();

    motor_busy = false;
}

static char http_response_buffer[2048] = {0};
static int http_response_index = 0;

static esp_err_t http_event_handler(esp_http_client_event_t *evt) {
    switch(evt->event_id) {
        case HTTP_EVENT_ON_DATA:
            if (http_response_index + evt->data_len < sizeof(http_response_buffer)) {
                memcpy(http_response_buffer + http_response_index, evt->data, evt->data_len);
                http_response_index += evt->data_len;
            }
            break;
        case HTTP_EVENT_ON_FINISH:
            http_response_buffer[http_response_index] = '\0';
            break;
        default:
            break;
    }
    return ESP_OK;
}

esp_err_t send_uid_to_server(char* uid_data) {
    if (motor_busy) {
        ESP_LOGW(TAG, "Motor busy");
        return ESP_OK;
    }

    esp_http_client_config_t config = {
        .url = SERVER_URL,
        .method = HTTP_METHOD_POST,
        .event_handler = http_event_handler,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);

    char post_data[128];
    uid_data[strcspn(uid_data, "\r\n")] = '\0';
    snprintf(post_data, sizeof(post_data), "{\"uid\":\"%s\"}", uid_data);

    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, post_data, strlen(post_data));

    memset(http_response_buffer, 0, sizeof(http_response_buffer));
    http_response_index = 0;

    esp_err_t err = esp_http_client_perform(client);
    if (err == ESP_OK) {
        int statusCode = esp_http_client_get_status_code(client);
        ESP_LOGI(TAG, "Status: %d", statusCode);

        if (statusCode == 200) {
            cJSON *root = cJSON_Parse(http_response_buffer);
            if (root == NULL) {
                ESP_LOGE(TAG, "JSON parse failed");
                esp_http_client_cleanup(client);
                return ESP_FAIL;
            }

            cJSON *status_item = cJSON_GetObjectItem(root, "status");
            if (status_item == NULL || !cJSON_IsString(status_item)) {
                ESP_LOGW(TAG, "No status field");
                cJSON_Delete(root);
                esp_http_client_cleanup(client);
                return ESP_OK;
            }

            char *status_str = status_item->valuestring;
            ESP_LOGI(TAG, "Status: %s", status_str);

            if (strcmp(status_str, "authorized") != 0) {
                ESP_LOGI(TAG, "Not authorized, skipping dispense");
                cJSON_Delete(root);
                esp_http_client_cleanup(client);
                return ESP_OK;
            }

            cJSON *seconds_item = cJSON_GetObjectItem(root, "portion_time");
            if (seconds_item == NULL) {
                seconds_item = cJSON_GetObjectItem(root, "seconds");
            }
            if (seconds_item == NULL) {
                seconds_item = cJSON_GetObjectItem(root, "duration");
            }

            int rotation_seconds = 2;
            if (seconds_item != NULL && cJSON_IsNumber(seconds_item)) {
                rotation_seconds = seconds_item->valueint;
                ESP_LOGI(TAG, "Portion time: %d s", rotation_seconds);
            }

            if (rotation_seconds < 1 || rotation_seconds > 30) {
                rotation_seconds = 2;
            }

            stepper_rotate_for_seconds(rotation_seconds);
            cJSON_Delete(root);
        }
    } else {
        ESP_LOGE(TAG, "HTTP failed: %s", esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    return err;
}

static void uart_rx_task(void *arg) {
    uint8_t* data = (uint8_t*) malloc(UART_BUF_SIZE);
    while (1) {
        int len = uart_read_bytes(UART_NUM, data, (UART_BUF_SIZE - 1), 20 / portTICK_PERIOD_MS);
        if (len) {
            data[len] = '\0';
            ESP_LOGI(TAG, "UID: %s", (char*)data);
            send_uid_to_server((char*)data);
        }
    }
}

void uart_init(void) {
    uart_config_t uart_config = {
        .baud_rate = 9600,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM, UART_BUF_SIZE * 2, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_NUM, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM, UART_TX_PIN, UART_RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
}

void app_main(void) {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
      ESP_ERROR_CHECK(nvs_flash_erase());
      ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    stepper_init();

    ESP_LOGI(TAG, "Startup test");
    stepper_rotate_for_seconds(2);

    wifi_init_sta();
    uart_init();
    xTaskCreate(uart_rx_task, "uart_rx_task", 4096, NULL, 10, NULL);
}
