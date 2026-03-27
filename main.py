import subprocess
import time

print("Motion detected! Python is taking over to record video...")

# File name for the output video
output_file = "motion_video.mp4"
record_time_ms = "10000" # 10000 milliseconds = 10 seconds

# Command to use the hardware encoder (libcamera-vid)
# --width and --height set to HD (1280x720) to keep Zero 2 W happy
cmd = [
    "libcamera-vid",
    "-t", record_time_ms,
    "--width", "1280",
    "--height", "720",
    "--framerate", "30",
    "--nopreview",
    "-o", output_file
]

try:
    print(f"Recording for {int(record_time_ms)/1000} seconds...")
    # Execute the command and wait for it to finish
    subprocess.run(cmd, check=True)
    print(f"Success! Video saved as '{output_file}'")
    
except subprocess.CalledProcessError as e:
    print(f"Error: Hardware encoder failed. Details: {e}")
except FileNotFoundError:
    print("Error: 'libcamera-vid' command not found. Is libcamera-apps installed?")