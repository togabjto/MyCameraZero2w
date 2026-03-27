import time
import subprocess
import os

print("--- Reverse Camera Lag Test (H.264 -> RAW -> H.264) ---")

# Step 1: Initial H.264 Warm-up (The "First Boot")
print("1. Initializing and warming up H.264 (Auto-focus & Exposure)...")
cmd_video = [
    "libcamera-vid",
    "-t", "1000",
    "--width", "1280",
    "--height", "720",
    "--nopreview",
    "-o", "warmup.mp4"
]
subprocess.run(cmd_video, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("Warm-up complete. Camera is now closed by libcamera.")

# Step 2: Measure H.264 -> RAW
print("2. Switching to RAW mode...")
start_to_raw = time.time()
try:
    fd = os.open("/dev/video0", os.O_RDWR)
except OSError:
    print("Error: Could not open /dev/video0.")
    exit()
end_to_raw = time.time()
lag_to_raw = end_to_raw - start_to_raw

time.sleep(1) # Pretend we are monitoring for a second

# Step 3: Measure RAW -> H.264 (The crucial test!)
print("3. Switching back to H.264 mode...")
start_to_h264 = time.time()

# Release RAW camera
os.close(fd)

# Start H.264 again
subprocess.run(cmd_video, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
end_to_h264 = time.time()

# Calculate H.264 lag (subtracting the 1 second record time)
lag_to_h264 = (end_to_h264 - start_to_h264) - 1.0

print("========================================")
print("               RESULTS                  ")
print("========================================")
print(f"Lag (H.264 -> RAW) : {lag_to_raw:.3f} seconds")
print(f"Lag (RAW -> H.264) : {lag_to_h264:.3f} seconds")
print("========================================")