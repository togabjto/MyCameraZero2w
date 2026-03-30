import os
import glob
import time
import ctypes
import numpy as np
import subprocess
from numpy.ctypeslib import ndpointer
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput

# ==========================================
# 1. Setup Directory
# ==========================================
MOVIE_DIR = "movie"
os.makedirs(MOVIE_DIR, exist_ok=True)

def get_next_file_number():
    files = glob.glob(os.path.join(MOVIE_DIR, "*.mp4"))
    max_num = 0
    for f in files:
        basename = os.path.basename(f)
        name, ext = os.path.splitext(basename)
        if name.isdigit():
            num = int(name)
            if num > max_num:
                max_num = num
    return max_num + 1

# ==========================================
# 2. Load C Library
# ==========================================
lib = ctypes.CDLL('./libmotion.so')
lib.detect_motion.argtypes = [ndpointer(ctypes.c_uint8, flags="C_CONTIGUOUS"), ctypes.c_int, ctypes.c_int]
lib.detect_motion.restype = ctypes.c_int

# ==========================================
# 3. Camera Setup
# ==========================================
picam2 = Picamera2()
config = picam2.create_video_configuration(
    main={"size": (1920, 1080), "format": "YUV420"}, 
    lores={"size": (320, 240), "format": "YUV420"}   
)
picam2.configure(config)
picam2.start()

# 【重要な修正】エンコーダ(録画チップ)は外で1回だけ作る！(フリーズ防止)
h264_encoder = H264Encoder(bitrate=2000000)

# flush=True をつけることで、文字化けせず確実にターミナルに表示させます
print("\n" + "="*40, flush=True)
print(" SYSTEM READY: Surveillance Camera", flush=True)
print(f" SAVE DIR: {os.path.abspath(MOVIE_DIR)}/", flush=True)
print("="*40 + "\n", flush=True)
time.sleep(2)

is_recording = False
record_until = 0
temp_filename = "temp_raw.h264"
current_file_num = 0

print("[WAITING] Monitoring for motion...", flush=True)

try:
    while True:
        current_time = time.time()

        # ==========================================
        # 4. Motion Detection
        # ==========================================
        try:
            lores_yuv = picam2.capture_array("lores")
        except Exception as e:
            # 万が一カメラが詰まってもエラー落ちさせずにスキップ
            print(f"[ERROR] Camera skipped a frame: {e}", flush=True)
            time.sleep(0.5)
            continue

        gray_frame = np.ascontiguousarray(lores_yuv[:240, :320])
        is_moving = lib.detect_motion(gray_frame, 320, 240)

        if is_moving == 1:
            record_until = current_time + 10.0

            if not is_recording:
                current_file_num = get_next_file_number()
                filename_base = f"{current_file_num:04d}" 
                
                print(f"\n[DETECTED] Motion! Starting record: {filename_base}.mp4", flush=True)
                
                output = FileOutput(temp_filename)
                picam2.start_recording(h264_encoder, output)
                is_recording = True
            else:
                # 録画中の延長ログ (英語)
                pass # ログがうるさい場合はこのようにpassにしておきます

        # ==========================================
        # 5. Stop Recording & Convert
        # ==========================================
        if is_recording and current_time >= record_until:
            picam2.stop_recording()
            is_recording = False
            time.sleep(0.5) # チップが落ち着くまで一瞬待つ（これ超大事）
            
            final_mp4 = os.path.join(MOVIE_DIR, f"{current_file_num:04d}.mp4")
            print(f"[STOP] No motion for 10s. Converting to MP4...", flush=True)
            
            subprocess.run(["ffmpeg", "-y", "-framerate", "30", "-i", temp_filename, "-c", "copy", final_mp4], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
                
            print(f"[SAVED] {final_mp4} has been saved successfully.", flush=True)
            print("-" * 40, flush=True)
            print("[WAITING] Resuming motion detection...", flush=True)
            print("-" * 40 + "\n", flush=True)

        time.sleep(0.05) 

except KeyboardInterrupt:
    print("\n\n[EXIT] Shutting down system...", flush=True)
finally:
    if is_recording:
        picam2.stop_recording()
        if os.path.exists(temp_filename):
            os.remove(temp_filename) 
    picam2.stop()
    print("[EXIT] Camera safely closed.", flush=True)