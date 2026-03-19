import cv2
import numpy as np
import subprocess
import time
import os
from datetime import datetime

# --- [Settings] ---
# 解析用画像を1/64（面積比）に小さくするので、閾値も小さめに設定します
THRESHOLD_AREA = 100  # 小さな動きも拾うなら50〜100、大きな物だけなら300〜
LEARNING_RATE = 0.05   # 少しゆっくり背景に馴染ませる設定
EXTEND_SECONDS = 5.0   # 動きが止まった後、何秒間録画を続けるか
SAVE_DIR = "movie"     # 保存先ディレクトリ

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# ラズパイ側の出力設定（10fps）
FPS_SETTING = 10.0

# --- [視野角最大化 + 720p / 10fps / GPUエンコード] ---
cmd = [
    "rpicam-vid",
    "-t", "0",
    "--inline",
    "-o", "-",
    "--width", "1280",    # 保存する動画の幅
    "--height", "720",    # 保存する動画の高さ
    "--framerate", str(int(FPS_SETTING)),
    "--codec", "h264",
    # --- [ここが視野角最大化のキモ] ---
    # センサーの最大解像度に近い値をビューファインダーに指定することで、
    # センサー全体を読み取ってからリサイズ（ダウンスケール）させます。
    "--viewfinder-width", "2304", 
    "--viewfinder-height", "1296",
    # -------------------------------
    "--profile", "high",
    "--level", "4.2",
    "--nopreview",
    "--flush",
    "--buffer-count", "6"
]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**6)

# 録画用変数
avg = None
out = None
is_recording = False
record_until = 0
fourcc = cv2.VideoWriter_fourcc(*'mp4v')

print(f"--- Surveillance Started (Saving to ./{SAVE_DIR}) ---")
print("Optimization: Motion detection is downsampled to 160x90.")

try:
    buffer = b""
    while True:
        # ストリームからJPGを切り出す
        buffer += proc.stdout.read(4096)
        a = buffer.find(b'\xff\xd8')
        b = buffer.find(b'\xff\xd9')
        
        if a != -1 and b != -1:
            jpg_data = buffer[a:b+2]
            buffer = buffer[b+2:]
            
            frame = cv2.imdecode(np.frombuffer(jpg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None: continue

            # --- [1. 解析用データの軽量化（ここが最大のポイント）] ---
            # 1280x720の全ピクセルを計算するとZero 2 Wは死ぬので、160x90に落とす
            search_frame = cv2.resize(frame, (160, 90))
            gray = cv2.cvtColor(search_frame, cv2.COLOR_BGR2GRAY)
            gray_blur = cv2.GaussianBlur(gray, (21, 21), 0)

            if avg is None:
                avg = gray_blur.copy().astype("float")
                continue

            # --- [2. 軽量データで動体検知計算] ---
            cv2.accumulateWeighted(gray_blur, avg, LEARNING_RATE)
            frame_delta = cv2.absdiff(gray_blur, cv2.convertScaleAbs(avg))
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            max_area = 0
            if contours:
                max_area = max([cv2.contourArea(c) for c in contours])

            # --- [3. 録画制御（保存は元の frame を使用）] ---
            current_time = time.time()
            timestamp_str = datetime.now().strftime("%H:%M:%S")

            if max_area > THRESHOLD_AREA:
                record_until = current_time + EXTEND_SECONDS
                if not is_recording:
                    filename = os.path.join(SAVE_DIR, datetime.now().strftime("%Y%m%d_%H%M%S.mp4"))
                    h, w = frame.shape[:2] # 1280x720を取得
                    # 動画ファイル側のFPSをrpicam-vidの設定(10.0)に合わせる
                    out = cv2.VideoWriter(filename, fourcc, FPS_SETTING, (w, h))
                    is_recording = True
                    print(f"\n[{timestamp_str}] >>> RECORDING STARTED: {filename}")

            if is_recording:
                out.write(frame) # 高画質なフレームを保存
                
                if current_time > record_until:
                    out.release()
                    is_recording = False
                    # 背景はリセットせず継続したほうが検知が安定します
                    print(f"\n[{timestamp_str}] <<< RECORDING STOPPED & SAVED")

            # ログ表示
            status = "REC" if is_recording else "---"
            print(f"\r[{timestamp_str}] Status: {status} | Area: {max_area:6.0f} ", end="", flush=True)

except KeyboardInterrupt:
    print("\nStopping...")
finally:
    if out: out.release()
    proc.terminate()
    print("Resources released.")