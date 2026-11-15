import time
import subprocess

print("--- Fair Camera Switch Lag Test ---")
print("Cycle: RAW -> H.264 -> RAW -> H.264\n")

def run_test(mode, cmd):
    print(f"Starting {mode} 1-second recording...")
    start_time = time.time()
    
    # Run the command silently
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Subtract exactly 1 second of recording time to find the setup/teardown lag
    lag = total_time - 1.0
    
    print(f"[{mode} Result] Total: {total_time:.3f}s | Pure Lag: {lag:.3f}s\n")
    return lag

# Commands for both modes
cmd_raw = ["libcamera-raw", "-t", "1000", "-o", "test_out.raw"]
cmd_h264 = ["libcamera-vid", "-t", "1000", "--width", "1280", "--height", "720", "--nopreview", "-o", "test_out.mp4"]

# --- Cycle 1 ---
print(">>> CYCLE 1 (Cold Start) <<<")
lag_raw_1 = run_test("RAW", cmd_raw)
lag_h264_1 = run_test("H.264", cmd_h264)

# --- Cycle 2 ---
print(">>> CYCLE 2 (Warm Start) <<<")
lag_raw_2 = run_test("RAW", cmd_raw)
lag_h264_2 = run_test("H.264", cmd_h264)

print("========================================")
print("             FINAL RESULTS              ")
print("========================================")
print(f"Cycle 1 RAW Lag   : {lag_raw_1:.3f} seconds")
print(f"Cycle 1 H.264 Lag : {lag_h264_1:.3f} seconds")
print("----------------------------------------")
print(f"Cycle 2 RAW Lag   : {lag_raw_2:.3f} seconds")
print(f"Cycle 2 H.264 Lag : {lag_h264_2:.3f} seconds")
print("========================================")