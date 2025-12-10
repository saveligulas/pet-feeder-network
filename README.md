# Smart Pet-Feeder

## Project

The project contains the necessary code to run the Smart Pet-Feeder using an Arduino Uno R3, ESP32C3 and a Raspberry Pi. The Project is also divided into these subdirectories: arduino, main, raspberry

### arduino

This directory contains both the .ino file for reading RFID Chips using the PN532 and transmitting uids to the ESP via UART, and the custom PN532 SPI Library to allow communication with the PN532.

### main

This directory contains the CMake file and source file for ESP-IDF. If you want to build this project you need to additionally add cJson as a component using the [IDF Component Manager](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/idf-component-manager.html).

#### pet-feeder-network.c

This file contains the entire code to be run on the ESP. The constants for WIFI_SSID and WIFI_PASS need to be adjusted to the same network the raspberry operates in. You then also have to set the Raspberrys Local IP correctly.

### raspberry

This directory contains the python files for running a the Http Server and SQLite database required to serve the frontend of our project.

