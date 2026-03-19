import cv2
import numpy as np
import subprocess
import time
import os
from datetime import datetime

# --- [Settings] ---
SAVE_DIR = "movie"
THRESHOLD_AREA = 1000 # 640x480用の感度
LEARNING_RATE = 0.1
RECORD_SECONDS = 10    # 1回の録画時間

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

def start_detection():
    """解析用のカメラプロセスを起動する"""
    cmd = [
        "rpicam-vid", "-t", "0", "--inline", "-o", "-", 
        "--width", "640", "--height", "480", "--nopreview", 
        "--framerate", "10", "--codec", "mjpeg"
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**6)

def record_high_quality(filename):
    """GPUを使って高画質録画を行う（この間、解析は止まる）"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] >>> GPU録画開始: {filename}")
    cmd = [
        "rpicam-vid",
        "-t", str(RECORD_SECONDS * 1000),
        "--inline",
        "-o", filename,
        "--width", "1280",
        "--height", "720",
        "--framerate", "20",
        "--codec", "h264", # GPU!
        "--nopreview"
    ]
    # 録画が終わるまで待機する
    subprocess.run(cmd)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] <<< 録画終了。解析に戻ります。")

# 最初の解析プロセスを起動
proc_detection = start_detection()
avg = None
buffer = b""

print("--- Surveillance System Online (Relay Mode) ---")

try:
    while True:
        # 解析用カメラからデータを読み込む
        data = proc_detection.stdout.read(4096)
        if not data: break
        buffer += data
        
        a = buffer.find(b'\xff\xd8')
        b = buffer.find(b'\xff\xd9')
        
        if a != -1 and b != -1:
            jpg_data = buffer[a:b+2]
            buffer = buffer[b+2:]
            
            frame = cv2.imdecode(np.frombuffer(jpg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None: continue

            # --- [動体検知ロジック] ---
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

            # ログ表示
            print(f"\rMonitoring... | Area: {max_area:6.0f} ", end="", flush=True)

            # --- [検知時のリレー処理] ---
            if max_area > THRESHOLD_AREA:
                # 1. 解析用プロセスを終了してカメラを解放する
                proc_detection.terminate()
                proc_detection.wait() # 完全に閉じるのを待つ
                
                # 2. 高画質GPU録画を実行
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(SAVE_DIR, f"{timestamp}.mp4")
                record_high_quality(filename)
                
                # 3. 解析用プロセスを再起動して監視に戻る
                print("カメラを再起動中...")
                time.sleep(1) # カメラの機嫌を直すための小休止
                proc_detection = start_detection()
                avg = None # 背景をリセット
                buffer = b""

except KeyboardInterrupt:
    print("\nStopping...")
finally:
    if proc_detection:
        proc_detection.terminate()