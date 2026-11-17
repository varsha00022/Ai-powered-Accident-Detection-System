# AI-Powered LoRa-Based Accident Detection and Emergency Alert System 
## Shreya K - 4CB23AI099
## Varsha M - 4CB23AI122

## Project Overview

The AI-Powered Accident Detection System Using LoRa is designed to detect vehicle accidents and transmit emergency alerts to a receiver, even in areas with limited or no mobile network connectivity.
The system uses a Machine Learning model to identify accident conditions based on vehicle movement data. LoRa communication is used to transmit accident alerts along with GPS location information to a receiver. A web-based dashboard displays accident status and related information.

## Objectives

Develop an AI-based system to detect vehicle accidents.

Identify normal and crash conditions using a Neural Network model.

Reduce false alerts through additional verification.

Transmit emergency alerts using LoRa communication.

Provide GPS location information for accident identification.

Display accident information through a web dashboard.

## Key Features

AI-Based Accident Detection: Uses a Neural Network model to distinguish between normal and crash conditions.

False Alert Reduction: Combines ML detection with IR-based verification.

LoRa Communication: Transmits emergency alerts without depending on mobile network connectivity.

GPS Location Tracking: Provides the location coordinates of the detected accident.

Web Dashboard: Displays accident status, prediction scores, GPS coordinates, and alert history.

## Dataset Used 
The dataset used in this project contains MPU6050 sensor readings collected for accident detection. It is used to train a neural network model to identify vehicle movement as either Normal or Crash.

The dataset contains:

Total Records: 4,689

Total Columns: 7

Input Features: 6

Target Column: label

Classes: Normal and Crash

The six input features are:

accel_x, accel_y, accel_z – Acceleration values along the X, Y, and Z axes.

gyro_x, gyro_y, gyro_z – Angular velocity values along the X, Y, and Z axes.

The dataset contains 4,007 Normal records and 682 Crash records.

## Software Used:

Arduino IDE: https://www.arduino.cc/en/software

Python: https://www.python.org/downloads/

Visual Studio Code: https://code.visualstudio.com/

Edge Impulse: https://edgeimpulse.com/

## Technologies Used

Category                        Technologies

Programming              -       Python, C++

Microcontroller          -       ESP32

Machine Learning         -       Neural Network, Edge Impulse

Communication            -       LoRa 

Location Tracking        -       GPS (NEO-6M)

Web Dashboard            -       Python, Flask

Development Tools        -       Arduino IDE, VS Code

Hardware Components      -       ESP32 Development Boards,  LoRa Transmitter and Receiver Modules,
                                 MPU6050 Accelerometer and Gyroscope,  GPS NEO-6M Module,
                                 IR Sensors,  RC Bluetooth Robot Car

## System Architecture

The project consists of two main units:

1. Transmitter Unit
Collects vehicle movement data.
Processes the data using the trained Neural Network model.
Performs additional verification using IR sensors.
Obtains GPS coordinates.
Sends accident alerts through LoRa.

3. Receiver Unit
Receives accident alerts through LoRa.
Transfers received information to the connected computer.
Displays accident information on the web dashboard.

## Working Principle

The AI-Powered Accident Detection System using LoRa works by combining sensor data collection, machine learning, IR sensor confirmation, GPS location tracking, and wireless communication. The system uses an RC Bluetooth robot car as a vehicle prototype, which is controlled through a mobile phone using Bluetooth commands. The MPU6050 sensor continuously measures acceleration and angular velocity along the X, Y, and Z axes and provides six input values to the trained neural network model developed using Edge Impulse. The ESP32 collects these readings approximately every 23.4 milliseconds and stores them in a sliding window. Once the window is full, the model performs inference and classifies the vehicle movement as either Normal or Crash. An accident is considered detected when two consecutive Crash predictions have a confidence score of at least 0.60. If a Crash is detected, the system checks whether the IR sensor has been triggered recently. An accident alert is generated only when both conditions are satisfied, which helps reduce false alerts caused by sudden movements during normal driving. After confirmation, the ESP32 obtains the available GPS coordinates from the NEO-6M GPS module and includes them in the accident alert message. The message is then transmitted to the receiver ESP32 through the LoRa module operating at 433 MHz. The MPU6050 sensor readings are also transmitted periodically every ten seconds. The receiver processes the incoming information and forwards it to a computer through serial communication. A Python script uses the PySerial library to receive and process the data, which is then displayed on the web dashboard developed using HTML, CSS, and JavaScript. The dashboard shows accident notifications, available GPS coordinates, sensor readings, prediction scores, and previous alerts. Leaflet and OpenStreetMap are used to display the accident location on an interactive map. The receiver ESP32 uses Wi-Fi for local dashboard connectivity, while LoRa is used to transmit information between the vehicle and receiver. This allows the system to detect possible accidents and share emergency information even in areas with limited mobile network connectivity.

## HOW TO RUN THE PROJECT:

Step 1: Install the required software, including Arduino IDE, Python and Visual Studio Code.

Step 2: Install the ESP32 board package in Arduino IDE and configure the required board settings.

Step 3: Install all the necessary Arduino libraries and Python packages required for the project.

Step 4: Connect the hardware components, including ESP32, MPU6050, GPS, IR sensors and LoRa modules, according to the circuit connections.

Step 5: Open the transmitter Arduino code and upload it to the transmitter ESP32.

Step 6: Open the receiver Arduino code and upload it to the receiver ESP32.

Step 7: Power ON both ESP32 boards and ensure that LoRa communication is established between the transmitter and receiver.

Step 8: Connect the receiver ESP32 to the computer using a USB cable.

Step 9: Open the Python dashboard project in Visual Studio Code and select the correct COM port and baud rate.

Step 10: Run the Python dashboard file to start monitoring the system.

Step 11: Control the robot car using Bluetooth commands and observe the live sensor readings.

Step 12: When an accident is detected and verified, the alert and available GPS coordinates are transmitted through LoRa and displayed on the dashboard.
