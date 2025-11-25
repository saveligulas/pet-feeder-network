// PN532_Custom.h
// Custom PN532 NFC/RFID library for Arduino (SPI mode only)
// Implements core functionality for reading ISO14443A cards

#ifndef PN532_CUSTOM_H
#define PN532_CUSTOM_H

#include <Arduino.h>
#include <SPI.h>

// ============================================================================
// PROTOCOL CONSTANTS
// ============================================================================

// PN532 Commands
#define PN532_COMMAND_GETFIRMWAREVERSION    (0x02)
#define PN532_COMMAND_SAMCONFIGURATION      (0x14)
#define PN532_COMMAND_INLISTPASSIVETARGET   (0x4A)

// Card Types
#define PN532_MIFARE_ISO14443A              (0x00)

// Frame structure bytes
#define PN532_PREAMBLE                      (0x00)
#define PN532_STARTCODE1                    (0x00)
#define PN532_STARTCODE2                    (0xFF)
#define PN532_POSTAMBLE                     (0x00)

// Host to PN532
#define PN532_HOSTTOPN532                   (0xD4)
// PN532 to Host
#define PN532_PN532TOHOST                   (0xD5)

// ACK and NACK
#define PN532_ACK_FRAME_SIZE                (6)

// SPI Status byte
#define PN532_SPI_STATREAD                  (0x02)
#define PN532_SPI_DATAWRITE                 (0x01)
#define PN532_SPI_DATAREAD                  (0x03)
#define PN532_SPI_READY                     (0x01)

// Timeouts
#define PN532_ACK_WAIT_TIME                 (10)  // milliseconds
#define PN532_DEFAULT_WAIT_TIME             (1000) // milliseconds


// ============================================================================
// MAIN CLASS
// ============================================================================

class PN532_Custom {
public:
    // Constructor - takes the Chip Select pin number
    PN532_Custom(uint8_t cs_pin);
    
    // Initialize the PN532 and SPI communication
    void begin();
    
    // Get the firmware version of the PN532 chip
    // Returns 32-bit version data, or 0 if failed
    uint32_t getFirmwareVersion();
    
    // Configure the Security Access Module (SAM)
    // Must be called before reading cards
    void SAMConfig();
    
    // Read a passive RFID target (card)
    // cardType: Type of card to read (use PN532_MIFARE_ISO14443A)
    // uid: Pointer to buffer to store the UID
    // uidLength: Pointer to variable that will receive the UID length
    // Returns: 1 if successful, 0 if failed or timeout
    uint8_t readPassiveTargetID(uint8_t cardType, uint8_t* uid, uint8_t* uidLength);

private:
    uint8_t _cs;     // Chip Select pin
    uint8_t _command; // Current command being processed
    
    // Low-level SPI communication functions
    void writeCommand(const uint8_t* cmd, uint8_t cmdlen);
    int8_t readResponse(uint8_t* buffer, uint8_t len, uint16_t timeout = PN532_DEFAULT_WAIT_TIME);
    bool isReady();
    bool waitReady(uint16_t timeout);
    bool readAck();
    
    // Utility functions
    void sendCommandCheckAck(const uint8_t* cmd, uint8_t cmdlen, uint16_t timeout = PN532_DEFAULT_WAIT_TIME);
};

#endif // PN532_CUSTOM_H