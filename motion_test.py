import cv2
import numpy as np
import subprocess
import time
from datetime import datetime

# --- [Settings] ---
THRESHOLD_AREA = 1000  # Detection sensitivity (Adjust this!)
LEARNING_RATE = 0.05   # Background learning speed

def capture_frame():
    # Use rpicam-still to output to stdout as JPG
    # --width/height: Lower resolution makes processing FASTER
    cmd = [
        "rpicam-still", 
        "-t", "1", 
        "-o", "-", 
        "--immediate", 
        "--nopreview", 
        "--width", "320", 
        "--height", "240"
    ]
    try:
        # Run command and grab the output (binary image)
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            # Convert binary JPG to OpenCV image (numpy array)
            nparr = np.frombuffer(result.stdout, np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"Capture Error: {e}")
    return None

avg = None
is_detecting = False

print("--- Raspberry Pi Motion Monitor (Subprocess Mode) ---")
print(" CTRL+C to stop")

try:
    while True:
        frame = capture_frame()
        if frame is None:
            continue

        # 1. Image Preprocessing (Gray and Blur)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_blur = cv2.GaussianBlur(gray, (21, 21), 0)

        if avg is None:
            print("Background model initialized.")
            avg = gray_blur.copy().astype("float")
            continue

        # 2. Difference Calculation (What moved?)
        cv2.accumulateWeighted(gray_blur, avg, LEARNING_RATE)
        frame_delta = cv2.absdiff(gray_blur, cv2.convertScaleAbs(avg))
        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
        
        # 3. Analyze contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        max_area = 0
        for c in contours:
            area = cv2.contourArea(c)
            if area > max_area:
                max_area = area

# 4. Console Logging (Overwriting the same line)
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Determine status string
        if max_area > THRESHOLD_AREA:
            status = " [!] MOTION DETECTED "
            # When motion starts, we can optionally print a new line to keep it in history
            # if is_detecting == False: print(f"\n[{timestamp}] Recording Triggered!")
            is_detecting = True
        else:
            status = " [-] Monitoring...  "
            is_detecting = False

        # \r moves the cursor to the start of the line. 
        # We add spaces at the end to clear any old long characters.
        print(f"\r[{timestamp}] {status} | Max Area: {max_area:6.0f}    ", end="", flush=True)
except KeyboardInterrupt:
    print("\nStopping...")