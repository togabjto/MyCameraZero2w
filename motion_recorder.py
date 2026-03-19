import cv2
import numpy as np
import subprocess
import time
import os
import shutil
from datetime import datetime

# --- [Settings] ---
SAVE_DIR = "movie"     # 保存先ディレクトリ
MAX_DISK_USAGE = 80    # SDカードの使用率が何%を超えたら古い動画を消すか
THRESHOLD_AREA = 100   # 動き検知の感度（160x90リサイズ用）
LEARNING_RATE = 0.05
EXTEND_SECONDS = 5.0   # 動きが止まった後の録画継続時間
FPS_SETTING = 10.0     # Zero 2 Wに最適なフレームレート

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# --- [Functions] ---
def cleanup_disk():
    """SDカードの空き容量をチェックし、古い動画を削除する"""
    usage = shutil.disk_usage("/")
    percent = (usage.used / usage.total) * 100
    if percent > MAX_DISK_USAGE:
        # 保存ディレクトリ内のファイルを古い順に並べる
        files = [os.path.join(SAVE_DIR, f) for f in os.listdir(SAVE_DIR) if f.endswith('.mp4')]
        files.sort(key=os.path.getmtime)
        if files:
            print(f"\n[Disk Cleanup] Usage {percent:.1f}% exceeds {MAX_DISK_USAGE}%. Deleting: {files[0]}")
            os.remove(files[0])

# --- [rpicam-vid Command] ---
cmd = [
    "rpicam-vid",
    "-t", "0",
    "--inline",
    "-o", "-",
    "--width", "1280",    # 録画解像度
    "--height", "720",
    "--framerate", str(int(FPS_SETTING)),
    "--codec", "h264",
    "--viewfinder-width", "2304", # 視野角最大化のための設定
    "--viewfinder-height", "1296",
    "--profile", "high",
    "--level", "4.2",
    "--nopreview",
    "--flush",
    "--buffer-count", "6"
]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**6)

# --- [Variables] ---
avg = None
out = None
is_recording = False
record_until = 0
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
buffer = b"" # バイナリバッファ

print(f"--- Surveillance Fully Optimized (Saving to ./{SAVE_DIR}) ---")

try:
    while True:
        # カメラからバイナリデータを読み込み
        data = proc.stdout.read(4096)
        if not data: break
        buffer += data
        
        # JPGの区切り（FF D8 ... FF D9）を探す
        a = buffer.find(b'\xff\xd8')
        b = buffer.find(b'\xff\xd9')
        
        if a != -1 and b != -1:
            jpg_data = buffer[a:b+2]
            buffer = buffer[b+2:]
            
            # 画像デコード
            frame = cv2.imdecode(np.frombuffer(jpg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None: continue

            # 1. 負荷軽減のために解析用画像をリサイズ
            search_frame = cv2.resize(frame, (160, 90))
            gray = cv2.cvtColor(search_frame, cv2.COLOR_BGR2GRAY)
            gray_blur = cv2.GaussianBlur(gray, (21, 21), 0)

            if avg is None:
                avg = gray_blur.copy().astype("float")
                continue

            # 2. 動体検知計算
            cv2.accumulateWeighted(gray_blur, avg, LEARNING_RATE)
            frame_delta = cv2.absdiff(gray_blur, cv2.convertScaleAbs(avg))
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            max_area = 0
            if contours:
                max_area = max([cv2.contourArea(c) for c in contours])

            # 3. 録画制御
            current_time = time.time()
            timestamp_str = datetime.now().strftime("%H:%M:%S")

            if max_area > THRESHOLD_AREA:
                record_until = current_time + EXTEND_SECONDS
                if not is_recording:
                    # 録画開始前にディスク掃除を実行
                    cleanup_disk()
                    
                    filename = os.path.join(SAVE_DIR, datetime.now().strftime("%Y%m%d_%H%M%S.mp4"))
                    h, w = frame.shape[:2]
                    out = cv2.VideoWriter(filename, fourcc, FPS_SETTING, (w, h))
                    is_recording = True
                    print(f"\n[{timestamp_str}] >>> REC START: {filename}")

            if is_recording:
                out.write(frame) # 高画質フレームを書き込み
                
                if current_time > record_until:
                    out.release()
                    is_recording = False
                    print(f"\n[{timestamp_str}] <<< REC STOPPED")

            # ログ表示
            status = "REC" if is_recording else "---"
            print(f"\r[{timestamp_str}] Status: {status} | Area: {max_area:6.0f} ", end="", flush=True)

except KeyboardInterrupt:
    print("\nStopping...")
finally:
    if out: out.release()
    proc.terminate()
    print("Resources released.")