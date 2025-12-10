#include "PN532_Custom.h"

PN532_Custom::PN532_Custom(uint8_t cs_pin) {
    _cs = cs_pin;
    _command = 0;
}

void PN532_Custom::begin() {
    pinMode(_cs, OUTPUT);
    digitalWrite(_cs, HIGH);

    SPI.begin();
    SPI.setDataMode(SPI_MODE0);
    SPI.setBitOrder(LSBFIRST);
    SPI.setClockDivider(SPI_CLOCK_DIV16);

    delay(100);
}

uint32_t PN532_Custom::getFirmwareVersion() {
    uint8_t response[12];
    uint8_t cmd[] = {PN532_COMMAND_GETFIRMWAREVERSION};

    sendCommandCheckAck(cmd, sizeof(cmd), 1000);

    if (readResponse(response, sizeof(response), 1000) < 0) {
        return 0;
    }

    // parse: D5 03 (IC Ver Rev Support)
    uint32_t versiondata = response[1];
    versiondata <<= 8;
    versiondata |= response[2];
    versiondata <<= 8;
    versiondata |= response[3];
    versiondata <<= 8;
    versiondata |= response[4];

    return versiondata;
}

void PN532_Custom::SAMConfig() {
    // mode, timeout (0x14 * 50ms = 1s), IRQ
    uint8_t cmd[] = {
        PN532_COMMAND_SAMCONFIGURATION,
        0x01,
        0x14,
        0x01
    };

    sendCommandCheckAck(cmd, sizeof(cmd), 1000);

    uint8_t response[8];
    readResponse(response, sizeof(response), 1000);
}

uint8_t PN532_Custom::readPassiveTargetID(uint8_t cardType, uint8_t* uid, uint8_t* uidLength) {
    // MaxTg (one card), BrTy (0x00 ISO14443A)
    uint8_t cmd[] = {
        PN532_COMMAND_INLISTPASSIVETARGET,
        0x01,
        cardType
    };

    sendCommandCheckAck(cmd, sizeof(cmd), 1000);

    uint8_t response[20];
    int16_t responseLength = readResponse(response, sizeof(response), 1000);

    if (responseLength < 0) {
        return 0;
    }

    // response: D5 4B (NbTg, Tg, SENS_RES, SEL_RES, NFCID Length, NFCID)
    if (response[0] != (PN532_COMMAND_INLISTPASSIVETARGET + 1)) {
        return 0;
    }

    uint8_t numberOfTags = response[1];
    if (numberOfTags != 1) {
        return 0;
    }

    // skip NbTg(1), Tg(1), SENS_RES(2), SEL_RES(1) = 6 bytes
    uint8_t uidLengthPos = 6;
    *uidLength = response[uidLengthPos];

    for (uint8_t i = 0; i < *uidLength; i++) {
        uid[i] = response[uidLengthPos + 1 + i];
    }

    return 1;
}

void PN532_Custom::writeCommand(const uint8_t* cmd, uint8_t cmdlen) {
    // frame length = TFI(1) + Command Data + Checksum(1)
    uint8_t length = cmdlen + 1;

    digitalWrite(_cs, LOW);
    delay(2);

    SPI.transfer(PN532_SPI_DATAWRITE);

    // send frame: Preamble + Start Code + Length + LCS + TFI + Data + DCS + Postamble
    SPI.transfer(PN532_PREAMBLE);
    SPI.transfer(PN532_STARTCODE1);
    SPI.transfer(PN532_STARTCODE2);

    // LCS checksum
    SPI.transfer(length);
    SPI.transfer(~length + 1);

    // frame identifier
    SPI.transfer(PN532_HOSTTOPN532);

    // data checksum
    uint8_t checksum = PN532_HOSTTOPN532;
    for (uint8_t i = 0; i < cmdlen; i++) {
        SPI.transfer(cmd[i]);
        checksum += cmd[i];
    }

    // two's complement of checksum
    SPI.transfer(~checksum + 1);

    SPI.transfer(PN532_POSTAMBLE);

    digitalWrite(_cs, HIGH);

    _command = cmd[0];
}

int8_t PN532_Custom::readResponse(uint8_t* buffer, uint8_t len, uint16_t timeout) {
    if (!waitReady(timeout)) {
        return -1;
    }

    digitalWrite(_cs, LOW);
    delay(2);

    SPI.transfer(PN532_SPI_DATAREAD);

    // skip preambles and start codes
    SPI.transfer(0x00);
    SPI.transfer(0x00);
    SPI.transfer(0x00);

    uint8_t length = SPI.transfer(0x00);
    uint8_t lcs = SPI.transfer(0x00);

    // verify LCS checksum
    if ((uint8_t)(length + lcs) != 0) {
        digitalWrite(_cs, HIGH);
        return -1;
    }

    // frame identifier
    uint8_t tfi = SPI.transfer(0x00);
    if (tfi != PN532_PN532TOHOST) {
        digitalWrite(_cs, HIGH);
        return -1;
    }

    // remove TFI byte from length
    length -= 1;

    if (length > len) {
        digitalWrite(_cs, HIGH);
        return -1;
    }

    // read data and calculate checksum
    uint8_t checksum = PN532_PN532TOHOST;
    for (uint8_t i = 0; i < length; i++) {
        buffer[i] = SPI.transfer(0x00);
        checksum += buffer[i];
    }

    // verify DCS checksum
    uint8_t dcs = SPI.transfer(0x00);
    if ((uint8_t)(checksum + dcs) != 0) {
        digitalWrite(_cs, HIGH);
        return -1;
    }

    SPI.transfer(0x00);
    digitalWrite(_cs, HIGH);

    return length;
}

bool PN532_Custom::isReady() {
    digitalWrite(_cs, LOW);
    SPI.transfer(PN532_SPI_STATREAD);
    uint8_t status = SPI.transfer(0x00);
    digitalWrite(_cs, HIGH);

    return (status & PN532_SPI_READY) != 0;
}

bool PN532_Custom::waitReady(uint16_t timeout) {
    uint32_t startTime = millis();

    while (!isReady()) {
        if ((millis() - startTime) > timeout) {
            return false;
        }
        delay(10);
    }

    return true;
}

bool PN532_Custom::readAck() {
    if (!waitReady(PN532_ACK_WAIT_TIME)) {
        return false;
    }

    // ACK frame: 00 00 FF 00 FF 00
    uint8_t ackBuffer[PN532_ACK_FRAME_SIZE];
    const uint8_t expectedAck[] = {0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00};

    digitalWrite(_cs, LOW);
    delay(2);

    SPI.transfer(PN532_SPI_DATAREAD);

    for (uint8_t i = 0; i < PN532_ACK_FRAME_SIZE; i++) {
        ackBuffer[i] = SPI.transfer(0x00);
    }

    digitalWrite(_cs, HIGH);

    for (uint8_t i = 0; i < PN532_ACK_FRAME_SIZE; i++) {
        if (ackBuffer[i] != expectedAck[i]) {
            return false;
        }
    }

    return true;
}

void PN532_Custom::sendCommandCheckAck(const uint8_t* cmd, uint8_t cmdlen, uint16_t timeout) {
    writeCommand(cmd, cmdlen);
    delay(10);
}
