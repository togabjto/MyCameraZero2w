import time
import subprocess
import os

print("--- Camera Mode Switch Lag Test (Python Only) ---")

# Step 1: Open camera in RAW mode (simulating your motion detection state)
print("1. Simulating RAW mode monitoring...")
try:
    fd = os.open("/dev/video0", os.O_RDWR)
except OSError:
    print("Error: Could not open /dev/video0. Is it being used?")
    exit()

time.sleep(1) # Pretend we are monitoring for a second

# Step 2: Trigger switch to H.264
print("2. Motion detected! Switching to H.264 mode...")
start_switch_to_video = time.time()

# Release RAW camera (handing over the baton)
os.close(fd)

# Record 1 second of H.264 video using hardware encoder
cmd_video = [
    "libcamera-vid",
    "-t", "1000",
    "--width", "1280",
    "--height", "720",
    "--nopreview",
    "-o", "test_h264.mp4"
]
subprocess.run(cmd_video, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

end_video_record = time.time()

# Step 3: Switch back to RAW
print("3. Video recording finished. Switching back to RAW mode...")
start_switch_to_raw = time.time()

# Re-open RAW camera (grabbing the baton back)
fd = os.open("/dev/video0", os.O_RDWR)

end_switch_to_raw = time.time()

# Cleanup before exiting
os.close(fd)

# --- Calculations ---
# Time taken to release RAW, start encoder, and record 1 sec
total_video_phase = end_video_record - start_switch_to_video
# Subtract the 1 second actual recording time to get the exact overhead
lag_to_h264 = total_video_phase - 1.0

# Time taken to re-open the camera file descriptor
lag_to_raw = end_switch_to_raw - start_switch_to_raw

print("========================================")
print("               RESULTS                  ")
print("========================================")
print(f"Lag (RAW -> H.264) : {lag_to_h264:.3f} seconds")
print(f"Lag (H.264 -> RAW) : {lag_to_raw:.3f} seconds")
print("----------------------------------------")
print(f"Total Round Trip   : {(lag_to_h264 + lag_to_raw):.3f} seconds")
print("========================================")