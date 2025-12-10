# Smart Pet-Feeder

An automated pet feeding system that uses RFID identification to control portion dispensing, with daily feeding limits and cooldown periods per pet.

## Overview

The Smart Pet-Feeder is a distributed IoT system consisting of three main components that work together to provide automated, access-controlled pet feeding. Each pet is assigned a unique RFID tag that grants them access to the feeder on a schedule configured through a web interface. The system logs all feeding events and denials for monitoring and management.

### Key Features

- **Per-pet configuration**: Set portion sizes, cooldown periods, and daily feeding limits
- **RFID access control**: Only registered pets can trigger food dispensing
- **Real-time logging**: Track all feeding events and access denials
- **Web dashboard**: Manage pets and view live activity logs

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       WiFi Network (2.4GHz)                             │
└─────────────────┬───────────────────────────────────────────────────────┘
                  │
     ┌────────────┴────────────┐
     │                         │
     │                    ┌────▼──────────────────────────┐
     │                    │    Raspberry Pi               │
     │                    │  (Server + Database)          │
     │                    │                               │
     │                    │  ┌──────────────────────────┐ │
     │                    │  │ Flask HTTP Server        │ │
     │                    │  │ Port 5000                │ │
     │                    │  └──────────────────────────┘ │
     │                    │  ┌──────────────────────────┐ │
     │                    │  │ SQLite Database          │ │
     │                    │  │ (pets, feeding_logs)     │ │
     │                    │  └──────────────────────────┘ │
     │                    │  ┌──────────────────────────┐ │
     │                    │  │ Web Dashboard            │ │
     │                    │  │ (Management UI)          │ │
     │                    │  └──────────────────────────┘ │
     │                    └───────────────────────────────┘
     │                              ▲
     │                              │ HTTP POST
     │                         (UID + Response)
     │                              │
     │    ┌─────────────────────────▼──────────────────────┐
     │    │        ESP32C3 Microcontroller                 │
     │    │        (Central Controller)                    │
     │    │                                                │
     │    │  ┌──────────────┐  ┌──────────────────────┐    │
     │    │  │ WiFi Module  │  │ UART Interface       │    │
     │    │  │              │  │ (9600 baud)          │    │
     │    │  └──────────────┘  └──────────────────────┘    │ 
     │    │                          ▲                     │
     │    │                          │ UART RX (Pin 9)     │
     │    │  ┌──────────────────────┐│                     │
     │    │  │ Stepper Motor Driver │└───┐                 │
     │    │  │ (GPIO 0,1,3,5)       │    │                 │
     │    │  └──────────────────────┘    │                 │
     │    └──────────────────────────────┘─────────────────┘
     │                                   │                
     │    ┌──────────────────────────────▼──────────────┐
     │    │        Arduino Uno R3                       │
     │    │        (RFID Reader)                        │
     │    │                                             │
     │    │  ┌─────────────────────────┐                │
     │    │  │ PN532 RFID Reader       │                │
     │    │  │ (SPI Interface)         │                │
     │    │  │                         │                │
     │    │  │ Detects ISO14443A tags  │                │
     │    │  └─────────────────────────┘                │
     │    │           ▲                                 │
     │    │           │ SPI (CS Pin 10)                 │
     │    │  ┌────────▼─────────────────┐               │
     │    │  │ RFID Tags (Pet Cards)    │               │
     │    │  │ Detected & Read          │               │
     │    │  └──────────────────────────┘               │
     │    └─────────────────────────────────────────────┘
     │
     └─► ┌─────────────────────────────────────────────────┐
         │  Stepper Motor (Food Dispenser)                 │
         │  Controlled by ESP32 GPIO pins                  │
         │  Rotates based on portion_size configuration    │
         └─────────────────────────────────────────────────┘
```

### Data Flow

1. **RFID Scan**: Arduino detects a pet's RFID tag via PN532 reader
2. **UID Transmission**: Arduino sends UID to ESP32 via UART (9600 baud)
3. **Authorization Request**: ESP32 sends HTTP POST request to Raspberry Pi with the UID
4. **Rule Check**: Server verifies pet registration, cooldown, and daily limits in SQLite database
5. **Response**: Server returns authorization status and portion size
6. **Motor Control**: ESP32 drives stepper motor based on response (authorized feedings rotate motor)
7. **Logging**: Server logs all events (authorized, denied, unknown tags)

## Project Structure

```
├── arduino/
│   ├── library/
│   │   ├── PN532_Custom.cpp      # Custom RFID library implementation
│   │   └── PN532_Custom.h        # RFID library header
│   └── pn532_rfid_reader_arduino/
│       └── pn532_rfid_reader_arduino.ino  # Arduino sketch
├── main/
│   ├── CMakeLists.txt            # ESP-IDF build configuration
│   └── pet-feeder-network.c      # ESP32 main firmware
├── raspberry/
│   ├── db.py                     # Database initialization
│   └── server.py                 # Flask server & web interface
└── README.md
```

## How It Works

### Feeding Flow

1. **RFID Scan**: When a pet approaches the feeder with their RFID tag, the Arduino's PN532 reader detects it
2. **UID Transmission**: The Arduino sends the tag's unique identifier (UID) to the ESP32 via UART (9600 baud)
3. **Server Authorization**: The ESP32 sends the UID to the Raspberry Pi server via HTTP POST request
4. **Rule Verification**: The server checks:
   - If the pet is registered in the database
   - If daily feeding limit hasn't been exceeded
   - If the cooldown period from the last feeding has passed
5. **Dispensing or Denial**: 
   - If authorized: The ESP32 drives the stepper motor for the configured portion duration (default 2-30 seconds)
   - If denied: Motor does not activate; the denial is logged
6. **Logging**: All events (authorized feedings, denials) are recorded with timestamps

### Communication Protocols

- **Arduino <-> ESP32**: UART serial at 9600 baud
- **ESP32 <-> Raspberry Pi**: HTTP POST/GET requests over WiFi
- **Arduino <-> PN532**: SPI communication with custom frame protocol
- **ESP32 <-> Stepper Motor**: GPIO direct control with 8-step sequence pattern

## Setup & Configuration

### Arduino

1. Include the `PN532_Custom` library in your Arduino IDE
2. Flash `pn532_rfid_reader_arduino.ino` to your Arduino Uno R3
3. Wire PN532 to Arduino via SPI (CS pin 10) and configure serial output to pins 2 (RX) and 3 (TX)

### ESP32 (ESP-IDF)

1. Install [ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/)
2. Add cJSON as a component using the [IDF Component Manager](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/idf-component-manager.html)
3. **Edit `pet-feeder-network.c`**:
   - Set `ESP_WIFI_SSID` and `ESP_WIFI_PASS` to match your network
   - Set `SERVER_URL` to your Raspberry Pi's local IP (e.g., `http://192.168.1.100:5000/tag`)
4. Build and flash using `idf.py build && idf.py flash`

### Raspberry Pi

1. Install Python 3 and Flask: `pip install flask`
2. Navigate to the `raspberry` directory
3. Run the server: `python server.py`
4. Access the web dashboard at `http://localhost:5000` (or your Pi's IP)

## Core Components

### PN532_Custom Library (Arduino)

Custom SPI-based library for the PN532 RFID reader. Provides:
- **Firmware version detection** to verify chip connectivity
- **SAM configuration** for passive tag detection
- **UID reading** from ISO14443A MIFARE cards
- **Frame parsing** with LCS and DCS checksum validation

### ESP32 Firmware (`pet-feeder-network.c`)

Handles three main tasks:
- **WiFi initialization**: Connects to your network and manages connection state
- **UART reception**: Listens for RFID UIDs from Arduino in a FreeRTOS task
- **Stepper motor control**: Drives the 4-pin stepper motor with configurable rotation duration

Stepper motor uses an 8-step sequence pattern (full-step mode) at 10ms per step. Motor runs for duration calculated as `seconds × (1000ms / 10ms) = steps`.

### Flask Server (`server.py`)

REST API endpoints:
- **POST `/tag`**: Receives UID from ESP32, validates against database rules, returns authorization status and portion time
- **GET `/api/logs`**: Returns last 100 feeding logs (grouped by consecutive identical events)
- **POST `/api/logs/clear`**: Clears all feeding event logs
- **POST `/register`**: Registers a new pet with RFID UID and feeding parameters
- **POST `/delete/<id>`**: Removes a pet and associated logs
- **GET `/start_registration`**: Initiates tag scanning mode for registration
- **GET `/get_captured_uid`**: Retrieves the most recently scanned UID (for web UI)

## Database Schema

### `pets` table
```
id                INTEGER PRIMARY KEY
name              TEXT
rfid_uid          TEXT UNIQUE
portion_size      INTEGER (1-30 seconds)
cooldown_min      INTEGER (minutes between feedings)
max_daily_feeds   INTEGER (maximum meals per day)
```

### `feeding_logs` table
```
id                INTEGER PRIMARY KEY
pet_id            INTEGER
pet_name          TEXT
event_type        TEXT ("Dispensed", "Denied")
details           TEXT
timestamp         DATETIME
```

## Future Enhancements

- Configurable WiFi settings via on-device UI
- Mobile app for remote management
- Explicit support for multiple Feeders (although it theoretically already should work)
