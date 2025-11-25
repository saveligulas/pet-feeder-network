#ifndef PN532_CUSTOM_H
#define PN532_CUSTOM_H

#include <Arduino.h>
#include <SPI.h>

#define PN532_COMMAND_GETFIRMWAREVERSION    (0x02)
#define PN532_COMMAND_SAMCONFIGURATION      (0x14)
#define PN532_COMMAND_INLISTPASSIVETARGET   (0x4A)

// Card Type according to ISO standard
#define PN532_MIFARE_ISO14443A              (0x00)

// Frame
#define PN532_PREAMBLE                      (0x00)
#define PN532_STARTCODE1                    (0x00)
#define PN532_STARTCODE2                    (0xFF)
#define PN532_POSTAMBLE                     (0x00)

#define PN532_HOSTTOPN532                   (0xD4)
#define PN532_PN532TOHOST                   (0xD5)

#define PN532_ACK_FRAME_SIZE                (6)

// SPI
#define PN532_SPI_STATREAD                  (0x02)
#define PN532_SPI_DATAWRITE                 (0x01)
#define PN532_SPI_DATAREAD                  (0x03)
#define PN532_SPI_READY                     (0x01)

#define PN532_ACK_WAIT_TIME                 (10)
#define PN532_DEFAULT_WAIT_TIME             (1000)


class PN532_Custom {
public:
    PN532_Custom(uint8_t cs_pin);
    
    void begin();
    
    uint32_t getFirmwareVersion();
    
    void SAMConfig();

    // 1 if success 0 if fail
    uint8_t readPassiveTargetID(uint8_t cardType, uint8_t* uid, uint8_t* uidLength);

private:
    uint8_t _cs;
    uint8_t _command;

    // SPI communication
    void writeCommand(const uint8_t* cmd, uint8_t cmdlen);
    int8_t readResponse(uint8_t* buffer, uint8_t len, uint16_t timeout = PN532_DEFAULT_WAIT_TIME);
    bool isReady();
    bool waitReady(uint16_t timeout);
    bool readAck();
    
    void sendCommandCheckAck(const uint8_t* cmd, uint8_t cmdlen, uint16_t timeout = PN532_DEFAULT_WAIT_TIME);
};

#endif // PN532_CUSTOM_H