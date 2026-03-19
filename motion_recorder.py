import cv2
import numpy as np
import subprocess
import time
import os
from datetime import datetime

# --- [Settings] ---
THRESHOLD_AREA = 100   # 解析画像を160x90に落とすので、100〜200くらいが適正
LEARNING_RATE = 0.05
EXTEND_SECONDS = 5.0   # 動きが止まった後の録画継続時間
SAVE_DIR = "movie"
FPS_SETTING = 10.0     # Zero 2 Wで安定するフレームレート

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# --- [GPUエンコード (H.264) を使うコマンド] ---
cmd = [
    "rpicam-vid",
    "-t", "0",
    "--inline",
    "-o", "-",
    "--width", "1280",
    "--height", "720",
    "--framerate", str(int(FPS_SETTING)),
    "--codec", "h264",    # GPUを使用
    "--nopreview",
    "--flush"
]

# カメラプロセス起動
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**6)

# OpenCVのVideoCaptureでパイプから動画として受け取る
# これにより imdecode のエラー（Assertion failed）を回避します
cap = cv2.VideoCapture("pipe:0", cv2.CAP_FFMPEG)

# 録画用変数
avg = None
out = None
is_recording = False
record_until = 0
fourcc = cv2.VideoWriter_fourcc(*'mp4v')

print(f"--- Surveillance Started (GPU Accelerated / 10fps) ---")

try:
    while True:
        # 1フレーム読み込み
        ret, frame = cap.read()
        if not ret:
            break

        # --- [1. 解析用データの軽量化] ---
        # 1280x720をそのまま計算すると重いので、160x90に落としてCPUを休ませる
        search_frame = cv2.resize(frame, (160, 90))
        gray = cv2.cvtColor(search_frame, cv2.COLOR_BGR2GRAY)
        gray_blur = cv2.GaussianBlur(gray, (21, 21), 0)

        if avg is None:
            avg = gray_blur.copy().astype("float")
            continue

        # --- [2. 動体検知計算] ---
        cv2.accumulateWeighted(gray_blur, avg, LEARNING_RATE)
        frame_delta = cv2.absdiff(gray_blur, cv2.convertScaleAbs(avg))
        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        max_area = 0
        if contours:
            max_area = max([cv2.contourArea(c) for c in contours])

        # --- [3. 録画制御] ---
        current_time = time.time()
        timestamp_str = datetime.now().strftime("%H:%M:%S")

        if max_area > THRESHOLD_AREA:
            record_until = current_time + EXTEND_SECONDS
            if not is_recording:
                filename = os.path.join(SAVE_DIR, datetime.now().strftime("%Y%m%d_%H%M%S.mp4"))
                h, w = frame.shape[:2]
                # 保存も 10fps に合わせる
                out = cv2.VideoWriter(filename, fourcc, FPS_SETTING, (w, h))
                is_recording = True
                print(f"\n[{timestamp_str}] >>> RECORDING STARTED: {filename}")

        if is_recording:
            out.write(frame) # 高画質な元の frame を保存
            
            if current_time > record_until:
                out.release()
                is_recording = False
                print(f"\n[{timestamp_str}] <<< RECORDING STOPPED")

        # ログ表示
        status = "REC" if is_recording else "---"
        print(f"\r[{timestamp_str}] Status: {status} | Area: {max_area:6.0f} ", end="", flush=True)

except KeyboardInterrupt:
    print("\nStopping...")
finally:
    if out: out.release()
    cap.release()
    proc.terminate()
    print("Resources released.")