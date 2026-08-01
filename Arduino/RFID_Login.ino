/*
 * ============================================================================
 *  Project     : RFID-Based Authentication System
 *  File        : RFID_Login.ino
 *  Description : Reads RFID card UID using MFRC522 module, sends the UID
 *                to the PC over Serial (USB), waits for a response from the
 *                Python application ("GRANTED" or "DENIED"), and provides
 *                visual (LED) and audible (buzzer) feedback accordingly.
 *
 *  Hardware    : Arduino Uno, MFRC522 RFID Reader, Green LED, Red LED, Buzzer
 *
 * ============================================================================
 *
 *  WIRING (MFRC522 -> Arduino Uno):
 *    SDA (SS)  -> Pin 10
 *    SCK       -> Pin 13
 *    MOSI      -> Pin 11
 *    MISO      -> Pin 12
 *    IRQ       -> Not connected
 *    GND       -> GND
 *    RST       -> Pin 9
 *    3.3V      -> 3.3V   (MFRC522 is a 3.3V device, do NOT use 5V)
 *
 *  OTHER CONNECTIONS:
 *    Green LED -> Pin 5  (through ~220 ohm resistor) -> GND
 *    Red LED   -> Pin 6  (through ~220 ohm resistor) -> GND
 *    Buzzer    -> Pin 7  -> GND
 *
 *  SERIAL PROTOCOL (9600 baud):
 *    Arduino -> PC : "UID:<hex_uid>\n"      e.g. "UID:A1B2C3D4\n"
 *    PC -> Arduino : "GRANTED\n" or "DENIED\n"
 *
 *  NOTE: This firmware NEVER makes an authentication decision itself. It only
 *  reads and reports the UID. The Python application is solely responsible
 *  for verifying the UID and returning the final decision. This firmware
 *  does NOT interact with, bypass, or emulate the Windows login screen.
 * ============================================================================
 */

#include <SPI.h>
#include <MFRC522.h>

// ---------------------------------------------------------------------------
// Pin Definitions
// ---------------------------------------------------------------------------
constexpr uint8_t RFID_SS_PIN   = 10;
constexpr uint8_t RFID_RST_PIN  = 9;

constexpr uint8_t GREEN_LED_PIN = 5;
constexpr uint8_t RED_LED_PIN   = 6;
constexpr uint8_t BUZZER_PIN    = 7;

// ---------------------------------------------------------------------------
// Timing / Configuration Constants
// ---------------------------------------------------------------------------
constexpr uint32_t SERIAL_BAUD_RATE       = 9600;
constexpr uint32_t RESPONSE_TIMEOUT_MS    = 5000;
constexpr uint32_t FEEDBACK_DURATION_MS   = 1500;
constexpr uint32_t CARD_READ_COOLDOWN_MS  = 2000;
constexpr uint32_t IDLE_BLINK_INTERVAL_MS = 1000;

constexpr uint16_t TONE_GRANTED_HZ   = 2000;
constexpr uint16_t TONE_DENIED_HZ    = 400;
constexpr uint16_t TONE_STARTUP_HZ   = 1000;
constexpr uint16_t BEEP_SHORT_MS     = 150;
constexpr uint16_t BEEP_LONG_MS      = 400;

// ---------------------------------------------------------------------------
// Global Objects
// ---------------------------------------------------------------------------
MFRC522 mfrc522(RFID_SS_PIN, RFID_RST_PIN);

unsigned long lastCardReadTime = 0;
unsigned long lastIdleBlinkTime = 0;
bool idleLedState = false;

// ---------------------------------------------------------------------------
// Function Prototypes
// ---------------------------------------------------------------------------
void setupPins();
void playStartupSequence();
String readCardUID();
void sendUIDToPC(const String &uid);
String waitForPCResponse(uint32_t timeoutMs);
void handleGrantedFeedback();
void handleDeniedFeedback();
void handleTimeoutFeedback();
void resetIndicators();
void idleHeartbeat();

// ---------------------------------------------------------------------------
// setup()
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  while (!Serial) {
    ; // Wait for serial port to be ready
  }

  SPI.begin();
  mfrc522.PCD_Init();

  setupPins();
  resetIndicators();
  playStartupSequence();

  Serial.println(F("READY"));
}

// ---------------------------------------------------------------------------
// loop()
// ---------------------------------------------------------------------------
void loop() {
  idleHeartbeat();

  if (millis() - lastCardReadTime < CARD_READ_COOLDOWN_MS) {
    return;
  }

  if (!mfrc522.PICC_IsNewCardPresent()) {
    return;
  }

  if (!mfrc522.PICC_ReadCardSerial()) {
    return;
  }

  lastCardReadTime = millis();

  String uid = readCardUID();

  resetIndicators();
  sendUIDToPC(uid);

  String response = waitForPCResponse(RESPONSE_TIMEOUT_MS);

  if (response == "GRANTED") {
    handleGrantedFeedback();
  } else if (response == "DENIED") {
    handleDeniedFeedback();
  } else {
    handleTimeoutFeedback();
  }

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();

  resetIndicators();
}

// ---------------------------------------------------------------------------
// setupPins()
// ---------------------------------------------------------------------------
void setupPins() {
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, LOW);
  noTone(BUZZER_PIN);
}

// ---------------------------------------------------------------------------
// playStartupSequence()
// ---------------------------------------------------------------------------
void playStartupSequence() {
  digitalWrite(GREEN_LED_PIN, HIGH);
  digitalWrite(RED_LED_PIN, HIGH);
  tone(BUZZER_PIN, TONE_STARTUP_HZ, BEEP_SHORT_MS);
  delay(200);
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, LOW);
  delay(200);
}

// ---------------------------------------------------------------------------
// readCardUID()
// ---------------------------------------------------------------------------
String readCardUID() {
  String uidString = "";

  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) {
      uidString += "0";
    }
    uidString += String(mfrc522.uid.uidByte[i], HEX);
  }

  uidString.toUpperCase();
  return uidString;
}

// ---------------------------------------------------------------------------
// sendUIDToPC()
// ---------------------------------------------------------------------------
void sendUIDToPC(const String &uid) {
  Serial.print(F("UID:"));
  Serial.println(uid);
}

// ---------------------------------------------------------------------------
// waitForPCResponse()
// ---------------------------------------------------------------------------
String waitForPCResponse(uint32_t timeoutMs) {
  unsigned long startTime = millis();
  String incoming = "";

  while (millis() - startTime < timeoutMs) {
    if (Serial.available() > 0) {
      incoming = Serial.readStringUntil('\n');
      incoming.trim();

      if (incoming == "GRANTED" || incoming == "DENIED") {
        return incoming;
      }
    }
  }

  return "";
}

// ---------------------------------------------------------------------------
// handleGrantedFeedback()
// ---------------------------------------------------------------------------
void handleGrantedFeedback() {
  digitalWrite(GREEN_LED_PIN, HIGH);
  digitalWrite(RED_LED_PIN, LOW);

  tone(BUZZER_PIN, TONE_GRANTED_HZ, BEEP_SHORT_MS);
  delay(200);
  tone(BUZZER_PIN, TONE_GRANTED_HZ, BEEP_SHORT_MS);

  delay(FEEDBACK_DURATION_MS);
}

// ---------------------------------------------------------------------------
// handleDeniedFeedback()
// ---------------------------------------------------------------------------
void handleDeniedFeedback() {
  digitalWrite(RED_LED_PIN, HIGH);
  digitalWrite(GREEN_LED_PIN, LOW);

  tone(BUZZER_PIN, TONE_DENIED_HZ, BEEP_LONG_MS);
  delay(FEEDBACK_DURATION_MS);
}

// ---------------------------------------------------------------------------
// handleTimeoutFeedback()
// ---------------------------------------------------------------------------
void handleTimeoutFeedback() {
  for (uint8_t i = 0; i < 3; i++) {
    digitalWrite(RED_LED_PIN, HIGH);
    digitalWrite(GREEN_LED_PIN, LOW);
    tone(BUZZER_PIN, TONE_DENIED_HZ, 100);
    delay(150);

    digitalWrite(RED_LED_PIN, LOW);
    digitalWrite(GREEN_LED_PIN, HIGH);
    delay(150);
  }
  digitalWrite(GREEN_LED_PIN, LOW);
}

// ---------------------------------------------------------------------------
// resetIndicators()
// ---------------------------------------------------------------------------
void resetIndicators() {
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, LOW);
  noTone(BUZZER_PIN);
}

// ---------------------------------------------------------------------------
// idleHeartbeat()
// ---------------------------------------------------------------------------
void idleHeartbeat() {
  if (millis() - lastIdleBlinkTime >= IDLE_BLINK_INTERVAL_MS) {
    lastIdleBlinkTime = millis();
    idleLedState = !idleLedState;
    digitalWrite(GREEN_LED_PIN, idleLedState ? HIGH : LOW);
  }
}
