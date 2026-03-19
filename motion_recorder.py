import cv2
import numpy as np
import subprocess
import time
import os
from datetime import datetime

# --- [設定] ---
SAVE_DIR = "movie"
THRESHOLD_AREA = 1500  # 640x480用の感度
LEARNING_RATE = 0.1
RECORD_SECONDS = 10    # 検知した時に録画する秒数

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# 1. 解析用ストリーム (CPUに優しい低解像度MJPEG)
cmd_preview = [
    "rpicam-vid", "-t", "0", "--inline", "-o", "-", 
    "--width", "640", "--height", "480", "--nopreview", 
    "--framerate", "10", "--codec", "mjpeg"
]
proc_preview = subprocess.Popen(cmd_preview, stdout=subprocess.PIPE, bufsize=10**6)

avg = None
is_recording = False # 録画中かどうかのフラグ

print(f"--- Surveillance Started: Detection(CPU) & Recording(GPU) ---")

try:
    buffer = b""
    while True:
        # --- [ステップ1: CPUで動体検知] ---
        data = proc_preview.stdout.read(4096)
        if not data: break
        buffer += data
        
        a = buffer.find(b'\xff\xd8')
        b = buffer.find(b'\xff\xd9')
        
        if a != -1 and b != -1:
            jpg_data = buffer[a:b+2]
            buffer = buffer[b+2:]
            
            frame = cv2.imdecode(np.frombuffer(jpg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None: continue

            # グレースケールで解析
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray_blur = cv2.GaussianBlur(gray, (21, 21), 0)

            if avg is None:
                avg = gray_blur.copy().astype("float")
                continue

            cv2.accumulateWeighted(gray_blur, avg, LEARNING_RATE)
            frame_delta = cv2.absdiff(gray_blur, cv2.convertScaleAbs(avg))
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            max_area = 0
            if contours:
                max_area = max([cv2.contourArea(c) for c in contours])

            # --- [ステップ2: 録画が必要ならGPUを叩き起こす] ---
            if max_area > THRESHOLD_AREA and not is_recording:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(SAVE_DIR, f"{timestamp}.mp4")
                
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] >>> 動き検知！GPU録画開始: {filename}")
                
                # GPU録画コマンドを「非同期」で実行（解析を止めないため）
                # Popenを使って、Pythonとは別の窓口で録画させます
                cmd_record = [
                    "rpicam-vid",
                    "-t", str(RECORD_SECONDS * 1000), # 録画秒数
                    "--inline",
                    "-o", filename,
                    "--width", "1920",   # 録画はフルHD！
                    "--height", "1080",
                    "--framerate", "30",
                    "--codec", "h264",   # ★ここがGPU！
                    "--nopreview"
                ]
                # Popenで投げっぱなしにする
                subprocess.Popen(cmd_record)
                
                # 録画中フラグを立てて、録画が終わるまで待つ（簡易実装）
                is_recording = True
                record_start_time = time.time()

            # 録画終了の判定（簡易的に時間で管理）
            if is_recording:
                if time.time() - record_start_time > RECORD_SECONDS:
                    is_recording = False
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] <<< 録画終了")

            # ログ
            status = "REC" if is_recording else "---"
            print(f"\rStatus: {status} | Area: {max_area:6.0f} ", end="", flush=True)

except KeyboardInterrupt:
    print("\nStopping...")
finally:
    proc_preview.terminate()