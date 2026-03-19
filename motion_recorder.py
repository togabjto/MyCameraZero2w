import cv2
import numpy as np
import subprocess
import time
import os
from datetime import datetime

# --- [Settings] ---
THRESHOLD_AREA = 1500  # 感度（環境に合わせて調整して）
LEARNING_RATE = 0.1
EXTEND_SECONDS = 5.0   # 動きが止まった後、何秒間録画を続けるか
SAVE_DIR = "movie"     # 保存先ディレクトリ（相対パス）

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# カメラプロセス起動 (MJPEGストリーム)
cmd = [
    "rpicam-vid", "-t", "0", "--inline", "-o", "-", 
    "--width", "640", "--height", "480", "--nopreview", 
    "--framerate", "20", "--codec", "mjpeg"
]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**6)

# 録画用変数
avg = None
out = None
is_recording = False
record_until = 0
fourcc = cv2.VideoWriter_fourcc(*'mp4v') # mp4形式で保存

print(f"--- Surveillance Started (Saving to ./{SAVE_DIR}) ---")

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

            # --- [Motion Detection Logic] ---
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

            # --- [Recording Control] ---
            current_time = time.time()
            timestamp_str = datetime.now().strftime("%H:%M:%S")

            if max_area > THRESHOLD_AREA:
                # 動き検知：終了時刻を更新
                record_until = current_time + EXTEND_SECONDS
                if not is_recording:
                    # 新規録画開始
                    filename = os.path.join(SAVE_DIR, datetime.now().strftime("%Y%m%d_%H%M%S.mp4"))
                    h, w = frame.shape[:2]
                    out = cv2.VideoWriter(filename, fourcc, 20.0, (w, h))
                    is_recording = True
                    print(f"\n[{timestamp_str}] >>> RECORDING STARTED: {filename}")

            if is_recording:
                out.write(frame) # フレームを書き込み
                
                # 規定時間を過ぎたら録画停止
                if current_time > record_until:
                    out.release()
                    is_recording = False
                    avg = None # 背景をリセットして次の検知に備える
                    print(f"\n[{timestamp_str}] <<< RECORDING STOPPED & SAVED")

            # ログ表示（上書き）
            status = "REC" if is_recording else "---"
            print(f"\r[{timestamp_str}] Status: {status} | Area: {max_area:6.0f} ", end="", flush=True)

except KeyboardInterrupt:
    print("\nStopping...")
finally:
    if out: out.release()
    proc.terminate()
    print("Resources released.")