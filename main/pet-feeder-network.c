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

// For UART communication (the ESP-IDF way)
#include "driver/uart.h"
#include "driver/gpio.h"

// =================================================================
// === CONFIGURATION: EDIT THESE VALUES! ===========================
// =================================================================

// --- Wi-Fi Credentials ---
#define ESP_WIFI_SSID      "Wlang Hotspot"
#define ESP_WIFI_PASS      "9876543210"
#define ESP_MAXIMUM_RETRY  5

// --- Local Endpoint ---
#define SERVER_URL "http://10.232.102.48:5000/tag"

// --- UART Configuration for Uno ---
#define UART_NUM            UART_NUM_1      // Use UART1
#define UART_RX_PIN         9               // GPIO 9 for receiving data
#define UART_TX_PIN         10              // Not used, but required for config
#define UART_BUF_SIZE       (1024)

// --- Stepper Motor GPIO Configuration ---
#define STEPPER_PIN_IN1     3               // GPIO3 → ULN2003 IN1
#define STEPPER_PIN_IN2     0               // GPIO0 → ULN2003 IN2
#define STEPPER_PIN_IN3     1               // GPIO1 → ULN2003 IN3
#define STEPPER_PIN_IN4     5               // GPIO5 → ULN2003 IN4

// --- Stepper Motor Timing (in milliseconds) ---
#define STEPPER_DELAY_MS    10              // Delay between steps (10ms = slower, smoother)
#define STEPS_PER_REVOLUTION 2048           // 28BYJ-48 full rotation

// =================================================================
// === FORWARD DECLARATIONS ========================================
// =================================================================

void stepper_init(void);
void stepper_rotate(int num_steps, int direction);
void stepper_stop(void);
void stepper_set_step(int step);
void stepper_rotate_for_seconds(int duration_seconds);

// =================================================================
// === MAIN CODE: NO NEED TO EDIT BELOW HERE =======================
// =================================================================

static const char *TAG = "RFID_NETWORK";

// --- Wi-Fi Event Handling ---
// This is more complex than in Arduino. We need to handle connection events.
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
            ESP_LOGI(TAG, "retry to connect to the AP");
        } else {
            xEventGroupSetBits(s_wifi_event_group, WIFI_FAIL_BIT);
        }
        ESP_LOGI(TAG, "connect to the AP fail");
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        ESP_LOGI(TAG, "got ip:" IPSTR, IP2STR(&event->ip_info.ip));
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

    ESP_LOGI(TAG, "wifi_init_sta finished.");

    EventBits_t bits = xEventGroupWaitBits(s_wifi_event_group,
            WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
            pdFALSE,
            pdFALSE,
            portMAX_DELAY);

    if (bits & WIFI_CONNECTED_BIT) {
        ESP_LOGI(TAG, "connected to ap SSID:%s", ESP_WIFI_SSID);
    } else if (bits & WIFI_FAIL_BIT) {
        ESP_LOGI(TAG, "Failed to connect to SSID:%s", ESP_WIFI_SSID);
    } else {
        ESP_LOGE(TAG, "UNEXPECTED EVENT");
    }
}

// =================================================================
// === STEPPER MOTOR FUNCTIONS =====================================
// =================================================================

/**
 * Initialize stepper motor GPIO pins as outputs
 */
void stepper_init(void) {
    ESP_LOGI(TAG, "Initializing stepper motor pins...");

    // Configure GPIO pins as outputs
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << STEPPER_PIN_IN1) | (1ULL << STEPPER_PIN_IN2) |
                        (1ULL << STEPPER_PIN_IN3) | (1ULL << STEPPER_PIN_IN4),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&io_conf);

    // Set all pins LOW initially
    gpio_set_level(STEPPER_PIN_IN1, 0);
    gpio_set_level(STEPPER_PIN_IN2, 0);
    gpio_set_level(STEPPER_PIN_IN3, 0);
    gpio_set_level(STEPPER_PIN_IN4, 0);

    ESP_LOGI(TAG, "✓ Stepper motor initialized on GPIO3(IN1), GPIO0(IN2), GPIO1(IN3), GPIO5(IN4)");
}

/**
 * Set coil state for 8-step full-step mode
 * Step 0-7 represent the 8 different coil combinations
 */
void stepper_set_step(int step) {
    // 8-step full-step sequence for 28BYJ-48
    int steps[8][4] = {
        {1, 0, 0, 0},  // Step 0: IN1 ON
        {1, 1, 0, 0},  // Step 1: IN1+IN2 ON
        {0, 1, 0, 0},  // Step 2: IN2 ON
        {0, 1, 1, 0},  // Step 3: IN2+IN3 ON
        {0, 0, 1, 0},  // Step 4: IN3 ON
        {0, 0, 1, 1},  // Step 5: IN3+IN4 ON
        {0, 0, 0, 1},  // Step 6: IN4 ON
        {1, 0, 0, 1},  // Step 7: IN4+IN1 ON
    };

    // Normalize step to 0-7 range
    step = step % 8;

    gpio_set_level(STEPPER_PIN_IN1, steps[step][0]);
    gpio_set_level(STEPPER_PIN_IN2, steps[step][1]);
    gpio_set_level(STEPPER_PIN_IN3, steps[step][2]);
    gpio_set_level(STEPPER_PIN_IN4, steps[step][3]);
}

/**
 * Rotate stepper motor by specified number of steps
 * direction: 1 = clockwise, -1 = counterclockwise
 */
void stepper_rotate(int num_steps, int direction) {
    ESP_LOGI(TAG, "→ Rotating motor %d steps in %s direction...",
             num_steps, direction > 0 ? "CLOCKWISE" : "COUNTERCLOCKWISE");

    static int current_step = 0;  // Track current step position

    for (int i = 0; i < num_steps; i++) {
        // Update step position based on direction
        current_step += direction;
        if (current_step < 0) {
            current_step = 7;  // Wrap around
        }

        // Apply step and delay
        stepper_set_step(current_step);
        vTaskDelay(STEPPER_DELAY_MS / portTICK_PERIOD_MS);
    }

    ESP_LOGI(TAG, "✓ Rotation complete!");
}

/**
 * Stop motor and de-energize coils (saves power)
 */
void stepper_stop(void) {
    gpio_set_level(STEPPER_PIN_IN1, 0);
    gpio_set_level(STEPPER_PIN_IN2, 0);
    gpio_set_level(STEPPER_PIN_IN3, 0);
    gpio_set_level(STEPPER_PIN_IN4, 0);
    ESP_LOGI(TAG, "Motor stopped and de-energized");
}

/**
 * Rotate motor for specified seconds (duration in seconds)
 */
void stepper_rotate_for_seconds(int duration_seconds) {
    // Calculate number of steps for the given duration
    // Each step takes STEPPER_DELAY_MS milliseconds
    // So steps_per_second = 1000 / STEPPER_DELAY_MS
    int steps_per_second = 1000 / STEPPER_DELAY_MS;
    int total_steps = duration_seconds * steps_per_second;

    ESP_LOGI(TAG, "🔄 Rotating for %d seconds (%d total steps)...", duration_seconds, total_steps);

    // Rotate forward
    stepper_rotate(total_steps, 1);

    // Hold position for 2 seconds
    vTaskDelay(2000 / portTICK_PERIOD_MS);

    // Rotate backward to return to starting position
    stepper_rotate(total_steps, -1);

    // De-energize
    stepper_stop();
}

// =================================================================
// === HTTP CLIENT & RESPONSE HANDLING =============================
// =================================================================

// Buffer for HTTP response body
static char http_response_buffer[2048] = {0};
static int http_response_index = 0;

// Callback to handle response data
static esp_err_t http_event_handler(esp_http_client_event_t *evt) {
    switch(evt->event_id) {
        case HTTP_EVENT_ON_DATA:
            // Append data to response buffer
            if (http_response_index + evt->data_len < sizeof(http_response_buffer)) {
                memcpy(http_response_buffer + http_response_index, evt->data, evt->data_len);
                http_response_index += evt->data_len;
            }
            break;
        case HTTP_EVENT_ON_FINISH:
            // Null-terminate the response
            http_response_buffer[http_response_index] = '\0';
            ESP_LOGI(TAG, "Response received: %s", http_response_buffer);
            break;
        default:
            break;
    }
    return ESP_OK;
}

/**
 * Send UID to server and handle response with dynamic rotation
 */
esp_err_t send_uid_to_server(char* uid_data) {
    esp_http_client_config_t config = {
        .url = SERVER_URL,
        .method = HTTP_METHOD_POST,
        .event_handler = http_event_handler,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);

    char post_data[128];

    // Trim newline or carriage return characters from uid_data
    uid_data[strcspn(uid_data, "\r\n")] = '\0';

    // Now safely build JSON
    snprintf(post_data, sizeof(post_data),
             "{\"uid\":\"%s\"}", uid_data);

    ESP_LOGI(TAG, "POST Body: %s", post_data);

    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, post_data, strlen(post_data));

    // Reset response buffer
    memset(http_response_buffer, 0, sizeof(http_response_buffer));
    http_response_index = 0;

    esp_err_t err = esp_http_client_perform(client);
    if (err == ESP_OK) {
        int statusCode = esp_http_client_get_status_code(client);
        ESP_LOGI(TAG, "HTTP POST Status = %d", statusCode);

        // ===== STEPPER MOTOR TRIGGER ON 200 RESPONSE =====
        if (statusCode == 200) {
            ESP_LOGI(TAG, "✓ Access granted! Parsing response...");

            // Parse JSON response to extract duration
            cJSON *root = cJSON_Parse(http_response_buffer);
            if (root == NULL) {
                ESP_LOGE(TAG, "❌ Failed to parse JSON response");
                ESP_LOGE(TAG, "Response was: %s", http_response_buffer);
                esp_http_client_cleanup(client);
                return ESP_FAIL;
            }

            // Extract "seconds" or "duration" field from JSON
            cJSON *seconds_item = cJSON_GetObjectItem(root, "portion_time");
            if (seconds_item == NULL) {
                seconds_item = cJSON_GetObjectItem(root, "duration");
            }

            int rotation_seconds = 2;  // Default value

            if (seconds_item != NULL && cJSON_IsNumber(seconds_item)) {
                rotation_seconds = seconds_item->valueint;
                ESP_LOGI(TAG, "✓ Extracted rotation duration: %d seconds", rotation_seconds);
            } else {
                ESP_LOGW(TAG, "⚠️  'seconds' or 'duration' field not found in JSON, using default: 2 seconds");
                ESP_LOGI(TAG, "Response JSON was: %s", http_response_buffer);
            }

            // Validate rotation duration (1-30 seconds reasonable limit)
            if (rotation_seconds < 1 || rotation_seconds > 30) {
                ESP_LOGW(TAG, "⚠️  Duration out of range (%d s), clamping to 2 seconds", rotation_seconds);
                rotation_seconds = 2;
            }

            // Perform rotation based on duration
            stepper_rotate_for_seconds(rotation_seconds);

            ESP_LOGI(TAG, "✓ Food dispensed!");

            cJSON_Delete(root);
        } else {
            ESP_LOGI(TAG, "Access denied (status %d)", statusCode);
        }
        // ===== END STEPPER MOTOR TRIGGER =====

    } else {
        ESP_LOGE(TAG, "HTTP POST request failed: %s", esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    return err;
}

// --- UART Task ---
// This task will run in the background, constantly listening for data from the Uno
static void uart_rx_task(void *arg) {
    uint8_t* data = (uint8_t*) malloc(UART_BUF_SIZE);
    while (1) {
        // Read data from the UART
        int len = uart_read_bytes(UART_NUM, data, (UART_BUF_SIZE - 1), 20 / portTICK_PERIOD_MS);
        if (len) {
            data[len] = '\0'; // Null-terminate the received data
            ESP_LOGI(TAG, "Received UID from Uno: %s", (char*)data);

            // Send the UID to the server
            send_uid_to_server((char*)data);
        }
    }
}

// --- UART Initialization ---
void uart_init(void) {
    uart_config_t uart_config = {
        .baud_rate = 9600,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    // Install UART driver
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM, UART_BUF_SIZE * 2, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_NUM, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM, UART_TX_PIN, UART_RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
}

// =================================================================
// === MAIN APPLICATION ============================================
// =================================================================

void app_main(void) {
    // This is the main function, like setup() in Arduino

    ESP_LOGI(TAG, "");
    ESP_LOGI(TAG, "╔═══════════════════════════════════════════════╗");
    ESP_LOGI(TAG, "║     PET FEEDER NETWORK INITIALIZING...        ║");
    ESP_LOGI(TAG, "╚═══════════════════════════════════════════════╝");
    ESP_LOGI(TAG, "");

    // Initialize NVS (Non-Volatile Storage), required for Wi-Fi
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
      ESP_ERROR_CHECK(nvs_flash_erase());
      ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
    ESP_LOGI(TAG, "✓ NVS initialized");

    // Initialize stepper motor
    stepper_init();
    ESP_LOGI(TAG, "✓ GPIO configured");

    // ===== STARTUP TEST: Simple startup rotation =====
    ESP_LOGI(TAG, "");
    ESP_LOGI(TAG, "════════════════════════════════════════════════");
    ESP_LOGI(TAG, "  🧪 STEPPER MOTOR STARTUP TEST");
    ESP_LOGI(TAG, "════════════════════════════════════════════════");

    ESP_LOGI(TAG, "Test: 2 second rotation...");
    stepper_rotate_for_seconds(2);

    ESP_LOGI(TAG, "════════════════════════════════════════════════");
    ESP_LOGI(TAG, "  ✅ STARTUP TEST COMPLETE!");
    ESP_LOGI(TAG, "════════════════════════════════════════════════");
    ESP_LOGI(TAG, "");
    // ===== END STARTUP TEST =====

    ESP_LOGI(TAG, "ESP_WIFI_MODE_STA");
    wifi_init_sta();

    // Initialize UART and start the listening task
    uart_init();
    xTaskCreate(uart_rx_task, "uart_rx_task", 4096, NULL, 10, NULL);
}
