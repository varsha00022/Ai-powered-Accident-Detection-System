# Ai-powered-Accident-Detection-System

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

2. Receiver Unit
Receives accident alerts through LoRa.
Transfers received information to the connected computer.
Displays accident information on the web dashboard.

## Working Principle

The MPU6050 collects acceleration and gyroscope data.
The Neural Network model analyses the collected data and identifies normal or crash conditions.
IR-based verification is used to help reduce false alerts.
When an accident condition is confirmed, GPS coordinates are obtained.
The transmitter sends the emergency alert through LoRa.
The receiver receives the alert and updates the web dashboard.
