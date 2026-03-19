import subprocess
import datetime
import os
import time

def take_still_image():
    # Use relative path: 'img' folder in the current directory
    save_dir = "img"
    
    # Create the directory if it does not exist
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        print(f"Created directory: {save_dir}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # Build the filename path
    filename = os.path.join(save_dir, f"image_{timestamp}.jpg")

    print(f"[{timestamp}] Capturing image with rpicam-still...")

    try:
        # Replaced 'libcamera-still' with 'rpicam-still' for 64-bit Lite OS
        # --immediate: no countdown, --nopreview: no GUI needed
        subprocess.run(["rpicam-still", "-o", filename, "--immediate", "--nopreview"], check=True)
        print(f"Save successful: {filename}")
    except subprocess.CalledProcessError as e:
        print(f"Capture Error: {e}")

if __name__ == "__main__":
    # Execute test capture
    take_still_image()