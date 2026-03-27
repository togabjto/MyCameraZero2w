import ctypes
import subprocess
import time

# Load the custom C library
motion_lib = ctypes.CDLL("./motion_lib.so")

print("--- Starting Switch Lag Test ---")

# 1. Initialize camera in RAW mode (Simulating monitoring state)
if motion_lib.init_camera() < 0:
    print("Error: Could not open camera in RAW mode.")
    exit()

print("Camera is in RAW mode. Pretend we just detected motion!")
time.sleep(1) # Simulating time spent monitoring

# 2. Start the timer!
print("Motion detected! Switching to H.264 mode...")
start_time = time.time()

# Release RAW camera
motion_lib.close_camera()

# Start libcamera-vid to record for exactly 1 second (1000 ms)
# Suppressing output so it doesn't clutter the console
cmd = [
    "libcamera-vid", 
    "-t", "1000", 
    "--width", "1280", 
    "--height", "720", 
    "--nopreview", 
    "-o", "test_lag.mp4"
]
subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# 3. Stop the timer!
end_time = time.time()

# 4. Calculate the results
total_time = end_time - start_time
# Subtract the 1 second of actual recording to find the setup/teardown overhead
lag = total_time - 1.0 

print("--- Test Complete ---")
print(f"Total time taken: {total_time:.3f} seconds")
print(f"Estimated switching lag: {lag:.3f} seconds")