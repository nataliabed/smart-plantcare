#include <WiFi.h>
#include <HTTPClient.h>
#include <Adafruit_NeoPixel.h>

// Pin Configuration
#define SOIL_SENSOR_PIN 32
#define PUMP_PIN 2
#define MATRIX_PIN 5
#define RING_PIN 23

#define NUM_MATRIX_PIXELS 64
#define NUM_RING_PIXELS 16

const char* ssid = "UAL-IoT";
const char* password = "$taffDevice2023";
const char* uploadURL = "https://backend-1-ku7v.onrender.com/upload";
const char* predictionURL = "https://backend-1-ku7v.onrender.com/predictions";
const char* deviceID = "ESP32_ABC123";  // ✅ Must match pattern: ESP32_XXXXXX

Adafruit_NeoPixel matrix(NUM_MATRIX_PIXELS, MATRIX_PIN, NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel ring(NUM_RING_PIXELS, RING_PIN, NEO_GRB + NEO_KHZ800);

int avgMoisture = 0;

void setup() {
  Serial.begin(115200);

  pinMode(PUMP_PIN, OUTPUT);
  digitalWrite(PUMP_PIN, LOW);

  matrix.begin();
  matrix.setBrightness(30);
  matrix.show();

  ring.begin();
  ring.setBrightness(50);
  ring.show();

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected!");
}

void loop() {
  int total = 0;
  for (int i = 0; i < 10; i++) {
    total += analogRead(SOIL_SENSOR_PIN);
    delay(100);
  }
  avgMoisture = total / 10;

  Serial.print("Average Soil Moisture: ");
  Serial.println(avgMoisture);

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(uploadURL);
    http.addHeader("Content-Type", "application/json");

    String payload = "{\"deviceID\":\"" + String(deviceID) + "\",\"avgMoisture\":" + String(avgMoisture) + "}";
    int httpCode = http.POST(payload);

    Serial.print("POST Response Code: ");
    Serial.println(httpCode);
    Serial.println(http.getString());

    http.end();
  }

  // Pump logic (water if soil is dry)
  if (avgMoisture < 1000) {
    digitalWrite(PUMP_PIN, HIGH);
    showWaterDrop();
    delay(3000);
    digitalWrite(PUMP_PIN, LOW);
    matrix.clear();
    matrix.show();
  }

  // Fetch prediction (camera from backend)
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(predictionURL);
    int httpCode = http.GET();
    if (httpCode == 200) {
      String response = http.getString();
      Serial.println("Prediction Response: " + response);

      // Simple check: if "healthy" is anywhere in latest prediction
      if (response.indexOf("healthy") >= 0) {
        showHappyFace();
      } else {
        showSadFace();
      }
    } else {
      Serial.print("Prediction fetch failed: ");
      Serial.println(httpCode);
    }
    http.end();
  }

  // Simulate grow light
  delay(5000);
  fillRing(ring.Color(150, 0, 150));

  delay(60000);  // Loop every minute
}

// Fill ring with color
void fillRing(uint32_t color) {
  for (int i = 0; i < NUM_RING_PIXELS; i++) {
    ring.setPixelColor(i, color);
  }
  ring.show();
}

// Fill matrix with solid color
void fillMatrix(uint32_t color) {
  for (int i = 0; i < NUM_MATRIX_PIXELS; i++) {
    matrix.setPixelColor(i, color);
  }
  matrix.show();
}

// Happy face on matrix + moisture bar
void showHappyFace() {
  matrix.clear();
  byte smile[8] = {
    B00100100,
    B00100100,
    B00000000,
    B01000010,
    B00111100,
    B00000000,
    B00000000,
    B00000000
  };
  for (int y = 0; y < 8; y++) {
    for (int x = 0; x < 8; x++) {
      int index = y * 8 + x;
      if (bitRead(smile[y], 7 - x)) {
        matrix.setPixelColor(index, matrix.Color(0, 255, 0));
      }
    }
  }
  drawMoistureBar();
  matrix.show();
}

// Sad face on matrix + moisture bar
void showSadFace() {
  matrix.clear();
  byte sad[8] = {
    B00100100,
    B00100100,
    B00000000,
    B00000000,
    B00111100,
    B01000010,
    B00000000,
    B00000000
  };
  for (int y = 0; y < 8; y++) {
    for (int x = 0; x < 8; x++) {
      int index = y * 8 + x;
      if (bitRead(sad[y], 7 - x)) {
        matrix.setPixelColor(index, matrix.Color(255, 0, 0));
      }
    }
  }
  drawMoistureBar();
  matrix.show();
}

void showWaterDrop() {
  matrix.clear();
  byte drop[8] = {
    B00011000,
    B00011000,
    B00111100,
    B00111100,
    B01111110,
    B01111110,
    B00111100,
    B00011000
  };
  for (int y = 0; y < 8; y++) {
    for (int x = 0; x < 8; x++) {
      int index = y * 8 + x;
      if (bitRead(drop[y], 7 - x)) {
        matrix.setPixelColor(index, matrix.Color(0, 0, 255)); // Blue drop
      }
    }
  }
  matrix.show();
}

// === Draw moisture bar on bottom row ===
void drawMoistureBar() {
  int numLit = max(1, (int) map(avgMoisture, 0, 4095, 0, 8));
  for (int i = 0; i < numLit; i++) {
    int index = (7 * 8) + i;  // Row 7 (bottom), columns 0-7
    matrix.setPixelColor(index, matrix.Color(0, 0, 255));  // Blue
  }
}