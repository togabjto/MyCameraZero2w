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

print("\n" + "="*40, flush=True)
print(" SYSTEM READY: Surveillance Camera", flush=True)
print("="*40 + "\n", flush=True)
time.sleep(2)

is_recording = False
record_until = 0
current_file_num = 0
temp_filename = ""

print("[WAITING] Monitoring for motion...", flush=True)

try:
    while True:
        current_time = time.time()

        # ---------- デバッグログ追加 ----------
        # print("[DEBUG] Getting frame...", flush=True) # ログが多すぎる場合は消してください
        
        # 映像の取得（フリーズするなら絶対ココ！）
        lores_yuv = picam2.capture_array("lores")
        gray_frame = np.ascontiguousarray(lores_yuv[:240, :320])
        
        # print("[DEBUG] Frame OK", flush=True)
        # --------------------------------------

        is_moving = lib.detect_motion(gray_frame, 320, 240)

        if is_moving == 1:
            record_until = current_time + 10.0

            if not is_recording:
                current_file_num = get_next_file_number()
                filename_base = f"{current_file_num:04d}" 
                temp_filename = f"temp_{filename_base}.h264"
                
                print(f"\n[DETECTED] Motion! Starting record: {filename_base}.mp4", flush=True)
                print("[DEBUG] Starting encoder...", flush=True)
                
                # エンコーダを毎回新鮮な状態で作成
                encoder = H264Encoder(bitrate=2000000)
                output = FileOutput(temp_filename)
                picam2.start_recording(encoder, output)
                is_recording = True
                
                print("[DEBUG] Record is running.", flush=True)

        # ==========================================
        # 4. Stop Recording & Force Camera Reset
        # ==========================================
        if is_recording and current_time >= record_until:
            print(f"[STOP] No motion for 10s. Stopping record...", flush=True)
            picam2.stop_recording()
            is_recording = False
            
            # 🌟【究極の対策】カメラのパニックを治すため、一度完全にシャットダウンして再起動する
            print("[DEBUG] Resetting camera pipeline to prevent freeze...", flush=True)
            picam2.stop()      # カメラのメモリを完全解放！
            time.sleep(0.5)    # 息継ぎ
            picam2.start()     # 綺麗な状態で再起動！
            print("[DEBUG] Camera reset COMPLETE.", flush=True)
            
            # 裏方でMP4に変換
            final_mp4 = os.path.join(MOVIE_DIR, f"{current_file_num:04d}.mp4")
            print(f"[CONVERT] Converting to MP4 in background...", flush=True)
            cmd = f"ffmpeg -y -framerate 30 -i {temp_filename} -c copy {final_mp4} && rm {temp_filename}"
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            print("-" * 40, flush=True)
            print("[WAITING] Resuming motion detection...", flush=True)
            print("-" * 40 + "\n", flush=True)

        time.sleep(0.05) 

except KeyboardInterrupt:
    print("\n\n[EXIT] Shutting down system...", flush=True)
finally:
    if is_recording:
        picam2.stop_recording()
    picam2.stop()
    print("[EXIT] Camera safely closed.", flush=True)