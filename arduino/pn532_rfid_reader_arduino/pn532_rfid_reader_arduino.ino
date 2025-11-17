#include <SPI.h>
#include <Adafruit_PN532.h>
#include <SoftwareSerial.h>

// =================================================================
// === PIN CONFIGURATION ===========================================
// =================================================================

// --- PN532 RFID Reader (SPI Pins) ---
// These are the hardware SPI pins for the Uno. Do not change.
// SCK: 13, MOSI: 11, MISO: 12
// The Chip Select (CS) pin can be any digital pin. Pin 10 is standard.
#define PN532_CS   (10)

// --- Software Serial for ESP32 Communication ---
// We will create a virtual serial port to send data to the ESP32.
// We only need the TX (Transmit) pin for sending.
// Pin 3 will be our TX pin. Pin 2 is defined as RX but will not be used.
SoftwareSerial unoToEspSerial(2, 3); // RX Pin = 2, TX Pin = 3


// =================================================================
// === OBJECT INITIALIZATION =======================================
// =================================================================

// Initialize the PN532 library using the SPI hardware and our chosen CS pin.
Adafruit_PN532 nfc(PN532_CS);


// =================================================================
// === MAIN CODE ===================================================
// =================================================================

void setup() {
  // Start the standard USB serial connection for debugging on your computer.
  // This lets you see messages in the Arduino IDE's Serial Monitor.
  Serial.begin(115200);
  while (!Serial); // Wait for the serial monitor to connect.
  Serial.println("Uno RFID to ESP32 Gateway - Starting up...");

  // Start the SoftwareSerial port for communication WITH the ESP32.
  // The baud rate of 9600 MUST match what the ESP32 is configured to listen for.
  unoToEspSerial.begin(9600);

  // --- Initialize the PN532 Reader ---
  nfc.begin();

  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.println("--------------------------------------------------");
    Serial.println("Error: Didn't find PN532 board. Check your wiring!");
    Serial.println("--------------------------------------------------");
    while (1); // Halt the program if the reader isn't found.
  }

  // Found the board, print out the firmware version for confirmation.
  Serial.print("Found PN532 Chip PN5"); Serial.println((versiondata >> 24) & 0xFF, HEX);
  Serial.print("Firmware ver. "); Serial.print((versiondata >> 16) & 0xFF, DEC);
  Serial.print('.'); Serial.println((versiondata >> 8) & 0xFF, DEC);

  // Configure the PN532 to read RFID cards.
  nfc.SAMConfig();
  
  Serial.println("\nSetup complete. Waiting for an RFID card...");
  Serial.println("==========================================");
}


void loop() {
  uint8_t success;
  uint8_t uid[] = { 0, 0, 0, 0, 0, 0, 0 }; // Buffer to store the UID
  uint8_t uidLength;                      // Variable to store the length of the UID

  // Wait for an ISO14443A card to be scanned.
  // The nfc.readPassiveTargetID() function will wait until a card is found.
  success = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength);

  if (success) {
    Serial.println("Card Detected!");
    
    // Convert the raw UID byte array into a clean, printable Hexadecimal string.
    String uidString = "";
    for (uint8_t i = 0; i < uidLength; i++) {
      // Add a leading zero if the hex value is less than 0x10 (e.g., 0F instead of F)
      if (uid[i] < 0x10) {
        uidString += "0";
      }
      uidString += String(uid[i], HEX);
    }
    uidString.toUpperCase(); // Convert to uppercase for consistency (e.g., DEADBEEF)

    // --- Action 1: Print the UID to the Serial Monitor for debugging ---
    Serial.print("UID read: ");
    Serial.println(uidString);

    // --- Action 2: Send the UID to the ESP32 via the SoftwareSerial pin ---
    unoToEspSerial.println(uidString);
    Serial.println("--> UID sent to ESP32.");
    Serial.println("------------------------------------------");
    
    // Wait for one second before trying to read a new card.
    // This prevents spamming the ESP32 if a card is held on the reader.
    delay(1000);
  }
}