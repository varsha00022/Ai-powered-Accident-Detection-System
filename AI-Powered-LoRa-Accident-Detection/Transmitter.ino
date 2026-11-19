  // ===== ML ADDED: Edge Impulse model library (keep this as the FIRST include) =====
#include <mVarsha-project-1_inferencing.h>
// ===== END ML ADDED =====

#include <SPI.h>
#include <LoRa.h>
#include <TinyGPS++.h>
#include "BluetoothSerial.h"
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>

// ========== LoRa Pins ==========
#define ss   5
#define rst  14
#define dio0 2

// ========== IR Sensors ==========
#define IR1_PIN 4     // First IR
#define IR2_PIN 15    // Second IR

// ========== GPS ==========
#define RXD2 16
#define TXD2 17
#define GPS_BAUD 9600

// ========== L298N Motor Driver ==========
#define IN1 25
#define IN2 26
#define IN3 27
#define IN4 32

TinyGPSPlus gps;
HardwareSerial gpsSerial(2);
BluetoothSerial SerialBT;
Adafruit_MPU6050 mpu;

unsigned long lastSendTime = 0;
const unsigned long sendInterval = 3000;

unsigned long lastMPUTime = 0;
const unsigned long mpuInterval = 10000;  // 10 seconds

// =====================================================================
// ===== ML ADDED (START): crash model. Nothing above/below is changed ==
// =====================================================================
// How it works: every loop() pass, one MPU reading goes into a 1-second
// rolling window. About every 0.5 s the model checks that window.
// The IR alert is only allowed through when the model has said "Crash"
// (confidence >= 0.90) two times in a row AND an IR sensor was triggered
// within the last few seconds.

static_assert(EI_CLASSIFIER_RAW_SAMPLES_PER_FRAME == 6,
              "Model must use 6 axes: accel_x,y,z + gyro_x,y,z");

// ---- settings you can tune ----
const float CRASH_CONFIDENCE         = 0.60f;   // min "Crash" confidence
const int   CONSECUTIVE_REQUIRED     = 1;       // Crash results needed in a row
const int   INFERENCE_STRIDE         = 20;      // run model every 20 readings (~0.5 s)
const unsigned long IR_WINDOW_MS     = 4000;    // IR hit is remembered this long
const unsigned long SAMPLE_INTERVAL_US = 23400; // time between MPU readings (matches your training data)
const bool  ML_DEBUG                 = true;    // print [ML] lines in Serial Monitor
// --------------------------------

static float mlRing[EI_CLASSIFIER_RAW_SAMPLE_COUNT][6];
static float mlFeatures[EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE];
int  mlHead = 0;            // next write position (= oldest reading once full)
int  mlCount = 0;           // readings currently in the window
int  mlSinceInfer = 0;
int  mlStreak = 0;
bool mlCrashConfirmed = false;
bool mlStarted = false;
unsigned long mlLastSampleUs = 0;
unsigned long mlLastAlertSeen = 0;

bool irSeen1 = false, irSeen2 = false;
unsigned long irMs1 = 0, irMs2 = 0;

void mlReset() {
  mlHead = 0;
  mlCount = 0;
  mlSinceInfer = 0;
  mlStreak = 0;
  mlCrashConfirmed = false;
}

bool mlIrRecent(bool seen, unsigned long ms) {
  return seen && (millis() - ms <= IR_WINDOW_MS);
}

void mlLatchIR(bool ir1, bool ir2) {
  unsigned long now = millis();
  if (ir1) { irSeen1 = true; irMs1 = now; }
  if (ir2) { irSeen2 = true; irMs2 = now; }
}

void mlRunModel() {
  // copy the rolling window into a straight array, oldest reading first
  int idx = mlHead;
  for (int i = 0; i < EI_CLASSIFIER_RAW_SAMPLE_COUNT; i++) {
    for (int k = 0; k < 6; k++) {
      mlFeatures[i * 6 + k] = mlRing[idx][k];
    }
    idx = (idx + 1) % EI_CLASSIFIER_RAW_SAMPLE_COUNT;
  }

  signal_t signal;
  int err = numpy::signal_from_buffer(mlFeatures, EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE, &signal);
  if (err != 0) {
    Serial.printf("[ML] signal error (%d)\n", err);
    return;
  }

  ei_impulse_result_t result = {0};
  EI_IMPULSE_ERROR res = run_classifier(&signal, &result, false);
  if (res != EI_IMPULSE_OK) {
    Serial.printf("[ML] classifier error (%d)\n", (int)res);
    return;
  }

  float crashConf = 0, normalConf = 0;
  for (size_t ix = 0; ix < EI_CLASSIFIER_LABEL_COUNT; ix++) {
    if (strcmp(result.classification[ix].label, "Crash") == 0) {
      crashConf = result.classification[ix].value;
    } else if (strcmp(result.classification[ix].label, "Normal") == 0) {
      normalConf = result.classification[ix].value;
    }
  }

  if (crashConf >= CRASH_CONFIDENCE) mlStreak++;
  else mlStreak = 0;
  mlCrashConfirmed = (mlStreak >= CONSECUTIVE_REQUIRED);

  if (ML_DEBUG) {
    bool irOk = mlIrRecent(irSeen1, irMs1) || mlIrRecent(irSeen2, irMs2);
    Serial.printf("[ML] Crash=%.2f Normal=%.2f streak=%d IR=%s\n",
                  crashConf, normalConf, mlStreak, irOk ? "yes" : "no");
  }
}

// Called once per loop(): takes one MPU reading and runs the model when due
void mlUpdate() {
  if (mlStarted) {
    unsigned long gap = micros() - mlLastSampleUs;
    if (gap > 3UL * SAMPLE_INTERVAL_US) {
      // loop was blocked (e.g. a LoRa send): window has a hole, start fresh
      mlReset();
    } else {
      // keep the spacing between readings the same as in the training data
      while ((unsigned long)(micros() - mlLastSampleUs) < SAMPLE_INTERVAL_US) { }
    }
  }
  mlStarted = true;
  mlLastSampleUs = micros();

  sensors_event_t a, g, t;
  mpu.getEvent(&a, &g, &t);

  // order MUST match training: accel_x,y,z then gyro_x,y,z
  mlRing[mlHead][0] = a.acceleration.x;
  mlRing[mlHead][1] = a.acceleration.y;
  mlRing[mlHead][2] = a.acceleration.z;
  mlRing[mlHead][3] = g.gyro.x;
  mlRing[mlHead][4] = g.gyro.y;
  mlRing[mlHead][5] = g.gyro.z;
  mlHead = (mlHead + 1) % EI_CLASSIFIER_RAW_SAMPLE_COUNT;
  if (mlCount < EI_CLASSIFIER_RAW_SAMPLE_COUNT) mlCount++;

  mlSinceInfer++;
  if (mlCount == EI_CLASSIFIER_RAW_SAMPLE_COUNT && mlSinceInfer >= INFERENCE_STRIDE) {
    mlSinceInfer = 0;
    mlRunModel();
  }
}

// After your code sends an alert (it updates lastSendTime), start fresh
void mlAfterAlert() {
  if (lastSendTime != mlLastAlertSeen) {
    mlLastAlertSeen = lastSendTime;
    mlReset();
    irSeen1 = false;
    irSeen2 = false;
  }
}
// =====================================================================
// ===== ML ADDED (END) ================================================
// =====================================================================

void setup() {
  Serial.begin(115200);
  while (!Serial);
  delay(1000);

  pinMode(IR1_PIN, INPUT);
  pinMode(IR2_PIN, INPUT);

  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  stopMotors();

  gpsSerial.begin(GPS_BAUD, SERIAL_8N1, RXD2, TXD2);
  Serial.println("GPS Serial started");

  SerialBT.begin("AccidentRobot");
  Serial.println("Bluetooth Started! Name: AccidentRobot");

  // MPU6050
  Wire.begin(21, 22);
  if (!mpu.begin(0x68)) {
    Serial.println("Failed to find MPU6050 chip!");
    while (1) delay(10);
  }
  Serial.println("MPU6050 Found!");
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  // LoRa
  LoRa.setPins(ss, rst, dio0);
  if (!LoRa.begin(433E6)) {
    Serial.println("Starting LoRa failed!");
    while (1);
  }

  Serial.println("System Ready");
}

void loop() {
  // Continuously read GPS
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }

  // Bluetooth Motor Control
  if (SerialBT.available()) {
    char command = SerialBT.read();
    command = toupper(command);
    controlMotors(command);
  }

  // ========== Send pure MPU data every 10 seconds ==========
  if (millis() - lastMPUTime >= mpuInterval) {
    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);

    String mpuMessage = "MPU Data\n";
    mpuMessage += "Accel X: " + String(a.acceleration.x, 2) + 
                  " Y: " + String(a.acceleration.y, 2) + 
                  " Z: " + String(a.acceleration.z, 2) + " m/s2\n";
    mpuMessage += "Gyro  X: " + String(g.gyro.x, 2) + 
                  " Y: " + String(g.gyro.y, 2) + 
                  " Z: " + String(g.gyro.z, 2) + " rad/s\n";
    mpuMessage += "Temp: " + String(temp.temperature, 1) + " C";

    LoRa.beginPacket();
    LoRa.print(mpuMessage);
    LoRa.endPacket();

    Serial.println(">>> Sent pure MPU Data");
    lastMPUTime = millis();
  }

  // ========== Accident Detection (2 IR sensors) ==========
  bool ir1 = digitalRead(IR1_PIN) == LOW;
  bool ir2 = digitalRead(IR2_PIN) == LOW;

  // ===== ML ADDED: let the IR alert through only if the model confirms a crash =====
  mlUpdate();                  // one MPU reading + model check (when due)
  mlLatchIR(ir1, ir2);         // remember IR hits for a few seconds
  ir1 = mlIrRecent(irSeen1, irMs1) && mlCrashConfirmed;
  ir2 = mlIrRecent(irSeen2, irMs2) && mlCrashConfirmed;
  // ===== END ML ADDED =====

  if (ir1 || ir2) {
    unsigned long now = millis();

    if (now - lastSendTime >= sendInterval) {
      String message = "";

      if (ir1 && ir2) {
        message = "Major accident\n";
      } else {
        message = "Accident is Detected\n";
      }

      if (gps.location.isValid()) {
        float latitude  = gps.location.lat();
        float longitude = gps.location.lng();

        message += "LAT: " + String(latitude, 6) + "\n";
        message += "LONG: " + String(longitude, 6) + "\n";
        message += "SPEED (km/h): " + String(gps.speed.kmph()) + "\n";
        message += "ALT (m): " + String(gps.altitude.meters()) + "\n";
        message += "HDOP: " + String(gps.hdop.value() / 100.0) + "\n";
        message += "Satellites: " + String(gps.satellites.value()) + "\n";
        message += "UTC: " + String(gps.date.year()) + "/" + 
                   String(gps.date.month()) + "/" + 
                   String(gps.date.day()) + "," + 
                   String(gps.time.hour()) + ":" + 
                   String(gps.time.minute()) + ":" + 
                   String(gps.time.second()) + "\n";
        message += "Maps: https://www.google.com/maps?q=";
        message += String(latitude, 6) + "," + String(longitude, 6);
      } 
      else {
        message += "No GPS Fix yet";
      }

      LoRa.beginPacket();
      LoRa.print(message);
      LoRa.endPacket();

      Serial.println(">>> Sent Accident Alert");
      Serial.println(message);
      Serial.println("----------------------------------");

      lastSendTime = now;
    }
  }

  // ===== ML ADDED: after an alert was sent, start fresh =====
  mlAfterAlert();
  // ===== END ML ADDED =====

  delay(20);
}

// ========== Motor Control ==========
void controlMotors(char cmd) {
  switch (cmd) {
    case 'F':
      digitalWrite(IN1, LOW);
      digitalWrite(IN2, HIGH);
      digitalWrite(IN3, HIGH);
      digitalWrite(IN4, LOW);
      Serial.println("Forward"); 
      SerialBT.println("Forward");
      break;
    case 'B':
      digitalWrite(IN1, HIGH);
      digitalWrite(IN2, LOW);
      digitalWrite(IN3, LOW);
      digitalWrite(IN4, HIGH);
      Serial.println("Backward"); 
      SerialBT.println("Backward");
      break;
    case 'R':
      digitalWrite(IN1, LOW);
      digitalWrite(IN2, HIGH);
      digitalWrite(IN3, LOW);
      digitalWrite(IN4, HIGH);
      Serial.println("Right"); 
      SerialBT.println("Right");
      break;
    case 'L':
      digitalWrite(IN1, HIGH);
      digitalWrite(IN2, LOW);
      digitalWrite(IN3, HIGH);
      digitalWrite(IN4, LOW);
      Serial.println("Left"); 
      SerialBT.println("Left");
      break;
    case 'S':
      stopMotors();
      Serial.println("Stop"); 
      SerialBT.println("Stop");
      break;

      default:
      // ignore unknown commands
      break;
  }
}

void stopMotors() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}
