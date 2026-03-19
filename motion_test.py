import cv2
import time
import os
import numpy as np
from datetime import datetime

# --- [Settings] ---
# Threshold for motion detection (Adjust this value later)
THRESHOLD_AREA = 500  
# Learning rate for background subtraction
LEARNING_RATE = 0.05   

# Initialize camera for Raspberry Pi (using default index 0)
cap = cv2.VideoCapture(0)

# Variables for motion detection
avg = None
is_detecting = False

print("--- Raspberry Pi Motion Detection Test (No Recording) ---")
print(" Press [Ctrl+C] to stop")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        # 1. Prepare lightweight image for detection
        # Resize to 300x300 and convert to grayscale
        lores = cv2.resize(frame, (300, 300))
        gray = cv2.cvtColor(lores, cv2.COLOR_BGR2GRAY)
        gray_blur = cv2.GaussianBlur(gray, (21, 21), 0)

        if avg is None:
            print("Initializing background model...")
            avg = gray_blur.copy().astype("float")
            continue

        # 2. Background subtraction and thresholding
        cv2.accumulateWeighted(gray_blur, avg, LEARNING_RATE)
        frame_delta = cv2.absdiff(gray_blur, cv2.convertScaleAbs(avg))
        # This 'thresh' is what would look "white" where things move
        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
        
        # 3. Find contours and calculate max area
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        max_area = 0
        for c in contours:
            area = cv2.contourArea(c)
            if area > max_area:
                max_area = area

        # 4. Console Logging and Logic Trigger
        current_time = datetime.now().strftime("%H:%M:%S")
        
        if max_area > THRESHOLD_AREA:
            # Logic: If area exceeds threshold, it would start recording
            print(f"[{current_time}] MOTION DETECTED! Area: {max_area:6.0f} -> [START RECORDING LOG]")
            is_detecting = True
        else:
            # Idle status
            if is_detecting:
                print(f"[{current_time}] Motion stopped. Area: {max_area:6.0f} -> [STOP LOG]")
                is_detecting = False
            # Print area periodically to monitor
            print(f"[{current_time}] Monitoring... Max Area: {max_area:6.0f}", end="\r")

        # Small sleep to prevent 100% CPU usage
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nStopping monitor...")
finally:
    cap.release()
    print("Camera released.")