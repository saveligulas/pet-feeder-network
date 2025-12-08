#include <PN532_Custom.h>

#include <SPI.h>
#include <SoftwareSerial.h>

#define PN532_CS   (10)
SoftwareSerial unoToEspSerial(2, 3); // RX Pin 2 TX Pin 3

PN532 nfc(PN532_CS);

void setup() {
  Serial.begin(115220);
  while (!Serial);
  Serial.println("Uno RFID to ESP32 Gateway");
  unoToEspSerial.begin(9600);

  nfc.begin();

  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.println("Error: Pn532 board not found");
    while (1);
  }

  Serial.print("Pn532 found"); Serial.println((versiondata >> 24) & 0xFF, HEX);
  Serial.print("Firmware ver. "); Serial.print((versiondata >> 16) & 0xFF, DEC);
  Serial.print('.'); Serial.println((versiondata >> 8) & 0xFF, DEC);

  nfc.SAMConfig();
  
  Serial.println("\nSetup complete. Ready to scan");
}


void loop() {
  Serial.print("Waiting for card....");

  bool success;
  uint8_t uid[] = { 0, 0, 0, 0, 0, 0, 0 };
  uint8_t uidLength;

  success = nfc.readPassiveTargetID(uid, &uidLength);

  if (success) {
    Serial.println("Success!");

    String uidString = "";
    for (uint8_t i = 0; i < uidLength; i++) {
      if (uid[i] < 0x10) {
        uidString += "0";
      }
      uidString += String(uid[i], HEX);
    }
    uidString.toUpperCase();

    Serial.print("UID read: ");
    Serial.println(uidString);
    unoToEspSerial.println(uidString);
    Serial.println("UID sent to ESP32");

    delay(1000);
  } else {
    Serial.println("Failed. No card found.");
    delay(500);
  }
}