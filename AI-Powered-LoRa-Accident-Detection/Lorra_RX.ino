#include <SPI.h>
#include <LoRa.h>

#define ss   5
#define rst  14
#define dio0 2

void setup() {
  Serial.begin(115200);
  while (!Serial);
  delay(500);

  Serial.println("LoRa Accident + MPU Receiver");
  Serial.println("Waiting for data...\n");

  LoRa.setPins(ss, rst, dio0);
  if (!LoRa.begin(433E6)) {
    Serial.println("Starting LoRa failed!");
    while (1);
  }
}

void loop() {
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String received = "";
    while (LoRa.available()) {
      received += (char)LoRa.read();
    }

    Serial.println();
    Serial.println("========================================");

    if (received.startsWith("MPU Data")) {
      Serial.println("           MPU SENSOR DATA");
    } 
    else {
      Serial.println("        ACCIDENT ALERT RECEIVED");
    }

    Serial.println("========================================");
    Serial.println(received);
    Serial.print("RSSI: ");
    Serial.print(LoRa.packetRssi());
    Serial.print(" dBm   |   SNR: ");
    Serial.println(LoRa.packetSnr());
    Serial.println("========================================\n");
  }
}
