// PN532_Custom.cpp
// Implementation of PN532_Custom library

#include "PN532_Custom.h"

// ============================================================================
// CONSTRUCTOR
// ============================================================================

PN532_Custom::PN532_Custom(uint8_t cs_pin) {
    _cs = cs_pin;
    _command = 0;
}

// ============================================================================
// PUBLIC METHODS
// ============================================================================

void PN532_Custom::begin() {
    // Configure CS pin as output and set high (inactive)
    pinMode(_cs, OUTPUT);
    digitalWrite(_cs, HIGH);
    
    // Initialize SPI with PN532-compatible settings
    // PN532 supports up to 5MHz SPI clock
    SPI.begin();
    SPI.setDataMode(SPI_MODE0);
    SPI.setBitOrder(LSBFIRST);
    SPI.setClockDivider(SPI_CLOCK_DIV16); // 1MHz on 16MHz Arduino
    
    // Small delay to let the chip stabilize
    delay(100);
}

uint32_t PN532_Custom::getFirmwareVersion() {
    uint8_t response[12];
    
    // Build command: Get Firmware Version
    uint8_t cmd[] = {PN532_COMMAND_GETFIRMWAREVERSION};
    
    // Send command and wait for ACK
    sendCommandCheckAck(cmd, sizeof(cmd), 1000);
    
    // Read response
    if (readResponse(response, sizeof(response), 1000) < 0) {
        return 0; // Failed to read response
    }
    
    // Parse response
    // Response format: D5 03 [IC] [Ver] [Rev] [Support]
    // We combine these into a 32-bit value
    uint32_t versiondata = response[1]; // IC
    versiondata <<= 8;
    versiondata |= response[2]; // Ver
    versiondata <<= 8;
    versiondata |= response[3]; // Rev
    versiondata <<= 8;
    versiondata |= response[4]; // Support
    
    return versiondata;
}

void PN532_Custom::SAMConfig() {
    // Build command: SAM Configuration
    // Mode: 0x01 = Normal mode
    // Timeout: 0x14 = 20 * 50ms = 1 second timeout
    // IRQ: 0x01 = Use IRQ pin
    uint8_t cmd[] = {
        PN532_COMMAND_SAMCONFIGURATION,
        0x01, // Normal mode
        0x14, // Timeout (20 * 50ms = 1 second)
        0x01  // Use IRQ pin
    };
    
    // Send command and wait for ACK
    sendCommandCheckAck(cmd, sizeof(cmd), 1000);
    
    // Read response (should be simple ACK)
    uint8_t response[8];
    readResponse(response, sizeof(response), 1000);
}

uint8_t PN532_Custom::readPassiveTargetID(uint8_t cardType, uint8_t* uid, uint8_t* uidLength) {
    // Build command: InListPassiveTarget
    // MaxTg: 0x01 = Read one card at a time
    // BrTy: cardType (0x00 for ISO14443A)
    uint8_t cmd[] = {
        PN532_COMMAND_INLISTPASSIVETARGET,
        0x01,      // MaxTg - maximum 1 card
        cardType   // BrTy - Baud rate and card type
    };
    
    // Send command and wait for ACK
    sendCommandCheckAck(cmd, sizeof(cmd), 1000);
    
    // Read response - this may take a while as it waits for a card
    uint8_t response[20];
    int16_t responseLength = readResponse(response, sizeof(response), 1000);
    
    if (responseLength < 0) {
        return 0; // Timeout or error
    }
    
    // Check if we found any tags
    // Response format: D5 4B [NbTg] [Tg] [SENS_RES] [SEL_RES] [NFCID Length] [NFCID]
    if (response[0] != (PN532_COMMAND_INLISTPASSIVETARGET + 1)) {
        return 0; // Wrong response command
    }
    
    uint8_t numberOfTags = response[1];
    if (numberOfTags != 1) {
        return 0; // No tags found
    }
    
    // Parse the response to extract UID
    // Skip: command(1) + NbTg(1) + Tg(1) + SENS_RES(2) + SEL_RES(1) = 6 bytes
    uint8_t uidLengthPos = 6;
    *uidLength = response[uidLengthPos];
    
    // Copy UID to output buffer
    for (uint8_t i = 0; i < *uidLength; i++) {
        uid[i] = response[uidLengthPos + 1 + i];
    }
    
    return 1; // Success
}

// ============================================================================
// PRIVATE METHODS - LOW LEVEL SPI COMMUNICATION
// ============================================================================

void PN532_Custom::writeCommand(const uint8_t* cmd, uint8_t cmdlen) {
    // Calculate frame length: TFI(1) + Command Data + Checksum(1)
    uint8_t length = cmdlen + 1; // +1 for TFI byte
    
    // Begin SPI transaction
    digitalWrite(_cs, LOW);
    delay(2); // Small delay for chip to recognize CS low
    
    // Send data write indicator
    SPI.transfer(PN532_SPI_DATAWRITE);
    
    // Send frame: Preamble + Start Code + Length + LCS + TFI + Data + DCS + Postamble
    SPI.transfer(PN532_PREAMBLE);
    SPI.transfer(PN532_STARTCODE1);
    SPI.transfer(PN532_STARTCODE2);
    
    // Length and Length Checksum (LCS)
    SPI.transfer(length);
    SPI.transfer(~length + 1); // LCS = two's complement of length
    
    // Frame identifier: Host to PN532
    SPI.transfer(PN532_HOSTTOPN532);
    
    // Calculate data checksum while sending command
    uint8_t checksum = PN532_HOSTTOPN532;
    for (uint8_t i = 0; i < cmdlen; i++) {
        SPI.transfer(cmd[i]);
        checksum += cmd[i];
    }
    
    // Send Data Checksum (DCS) = two's complement of checksum
    SPI.transfer(~checksum + 1);
    
    // Send postamble
    SPI.transfer(PN532_POSTAMBLE);
    
    // End SPI transaction
    digitalWrite(_cs, HIGH);
    
    // Store command for later verification
    _command = cmd[0];
}

int8_t PN532_Custom::readResponse(uint8_t* buffer, uint8_t len, uint16_t timeout) {
    // Wait for PN532 to be ready with response
    if (!waitReady(timeout)) {
        return -1; // Timeout
    }
    
    // Begin SPI transaction
    digitalWrite(_cs, LOW);
    delay(2);
    
    // Send data read command
    SPI.transfer(PN532_SPI_DATAREAD);
    
    // Read frame header
    // Skip preamble and start codes
    SPI.transfer(0x00); // Dummy read for preamble
    SPI.transfer(0x00); // Dummy read for start code 1
    SPI.transfer(0x00); // Dummy read for start code 2
    
    // Read length
    uint8_t length = SPI.transfer(0x00);
    uint8_t lcs = SPI.transfer(0x00); // Length checksum
    
    // Verify length checksum
    if ((uint8_t)(length + lcs) != 0) {
        digitalWrite(_cs, HIGH);
        return -1; // Invalid length checksum
    }
    
    // Read frame identifier (should be PN532_PN532TOHOST = 0xD5)
    uint8_t tfi = SPI.transfer(0x00);
    if (tfi != PN532_PN532TOHOST) {
        digitalWrite(_cs, HIGH);
        return -1; // Invalid frame identifier
    }
    
    // Adjust length (remove TFI byte from count)
    length -= 1;
    
    // Check buffer size
    if (length > len) {
        digitalWrite(_cs, HIGH);
        return -1; // Buffer too small
    }
    
    // Read response data and calculate checksum
    uint8_t checksum = PN532_PN532TOHOST;
    for (uint8_t i = 0; i < length; i++) {
        buffer[i] = SPI.transfer(0x00);
        checksum += buffer[i];
    }
    
    // Read and verify data checksum
    uint8_t dcs = SPI.transfer(0x00);
    if ((uint8_t)(checksum + dcs) != 0) {
        digitalWrite(_cs, HIGH);
        return -1; // Invalid data checksum
    }
    
    // Read postamble (ignore)
    SPI.transfer(0x00);
    
    // End SPI transaction
    digitalWrite(_cs, HIGH);
    
    return length; // Return number of bytes read
}

bool PN532_Custom::isReady() {
    // Begin SPI transaction
    digitalWrite(_cs, LOW);
    
    // Send status read command
    SPI.transfer(PN532_SPI_STATREAD);
    
    // Read status byte
    uint8_t status = SPI.transfer(0x00);
    
    // End SPI transaction
    digitalWrite(_cs, HIGH);
    
    // Check if ready bit is set (bit 0)
    return (status & PN532_SPI_READY) != 0;
}

bool PN532_Custom::waitReady(uint16_t timeout) {
    uint32_t startTime = millis();
    
    // Poll until ready or timeout
    while (!isReady()) {
        if ((millis() - startTime) > timeout) {
            return false; // Timeout
        }
        delay(10); // Small delay between polls
    }
    
    return true; // Ready
}

bool PN532_Custom::readAck() {
    // Wait for PN532 to be ready
    if (!waitReady(PN532_ACK_WAIT_TIME)) {
        return false;
    }
    
    // ACK frame format: 00 00 FF 00 FF 00
    uint8_t ackBuffer[PN532_ACK_FRAME_SIZE];
    const uint8_t expectedAck[] = {0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00};
    
    // Begin SPI transaction
    digitalWrite(_cs, LOW);
    delay(2);
    
    // Send data read command
    SPI.transfer(PN532_SPI_DATAREAD);
    
    // Read ACK frame
    for (uint8_t i = 0; i < PN532_ACK_FRAME_SIZE; i++) {
        ackBuffer[i] = SPI.transfer(0x00);
    }
    
    // End SPI transaction
    digitalWrite(_cs, HIGH);
    
    // Verify ACK frame
    for (uint8_t i = 0; i < PN532_ACK_FRAME_SIZE; i++) {
        if (ackBuffer[i] != expectedAck[i]) {
            return false; // ACK verification failed
        }
    }
    
    return true; // ACK received successfully
}

void PN532_Custom::sendCommandCheckAck(const uint8_t* cmd, uint8_t cmdlen, uint16_t timeout) {
    // Send the command
    writeCommand(cmd, cmdlen);
    
    // Wait a bit for the PN532 to process
    delay(10);
    
    // Read and verify ACK
    if (!readAck()) {
        // ACK not received - could add error handling here
        // For now, we continue anyway (matching Adafruit library behavior)
    }
}