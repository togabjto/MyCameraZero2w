import subprocess
import datetime
import os
import time

def take_still_image():
    # Set the save directory to ~/MyC/img
    save_dir = os.path.expanduser("~/MyC/img")
    
    # Create the img directory if it does not exist
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        print(f"Created directory: {save_dir}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # Join path and filename
    filename = os.path.join(save_dir, f"image_{timestamp}.jpg")

    print(f"[{timestamp}] Capturing image...")

    try:
        # Execute capture command
        # --immediate: no delay, --nopreview: no window
        subprocess.run(["libcamera-still", "-o", filename, "--immediate", "--nopreview"], check=True)
        print(f"Save successful: {filename}")
    except subprocess.CalledProcessError as e:
        print(f"Capture Error: {e}")

if __name__ == "__main__":
    # Test capture
    take_still_image()