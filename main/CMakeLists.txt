idf_component_register(SRCS "pet-feeder-network.c"
        INCLUDE_DIRS "."
        REQUIRES esp_wifi esp_event nvs_flash esp_netif esp_http_client driver)

set(REQUIRES
    "esp_wifi"
    "esp_event"
    "esp_log"
    "nvs_flash"
    "esp_netif"
    "esp_http_client"
    "driver"
)