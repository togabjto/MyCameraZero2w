import cv2
import numpy as np
import subprocess
import time
import os
import shutil
from datetime import datetime

# --- [Settings] ---
SAVE_DIR = "movie"      # 保存先ディレクトリ
MAX_DISK_USAGE = 80     # SDカード使用率が80%を超えたら古い動画を削除
THRESHOLD_AREA = 100    # 動き検知の感度（160x90にリサイズ後の面積）
LEARNING_RATE = 0.05
EXTEND_SECONDS = 5.0    # 動きが止まった後の録画継続時間
FPS_SETTING = 10.0      # Zero 2 Wに最適なフレームレート（10fps）

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# --- [Functions] ---
def cleanup_disk():
    """SDカードの空き容量をチェックし、古い動画を削除する"""
    usage = shutil.disk_usage("/")
    percent = (usage.used / usage.total) * 100
    if percent > MAX_DISK_USAGE:
        files = [os.path.join(SAVE_DIR, f) for f in os.listdir(SAVE_DIR) if f.endswith('.mp4')]
        files.sort(key=os.path.getmtime)
        if files:
            print(f"\n[Disk Cleanup] Usage {percent:.1f}% exceeds {MAX_DISK_USAGE}%. Deleting: {files[0]}")
            os.remove(files[0])

# --- [rpicam-vid Command] ---
# フレームレート(10)とGPU(h264)と視野角(--viewfinder)をすべて統合
cmd = [
    "rpicam-vid",
    "-t", "0",
    "--inline",
    "-o", "-",
    "--width", "1280",
    "--height", "720",
    "--framerate", str(int(FPS_SETTING)), # 10fpsに固定
    "--codec", "h264",
    "--viewfinder-width", "2304", 
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
buffer = b"" # バイナリデータ用

print(f"--- Surveillance Fully Optimized (10fps / HD / FOV Max) ---")

try:
    while True:
        # 1. データの読み込み（少し多めに8KBずつ）
        data = proc.stdout.read(8192)
        if not data: break
        buffer += data
        
        # 2. JPEGの切り出しループ（バッファ詰まり対策）
        while True:
            a = buffer.find(b'\xff\xd8')
            b = buffer.find(b'\xff\xd9')
            
            if a != -1 and b != -1 and a < b:
                jpg_data = buffer[a:b+2]
                buffer = buffer[b+2:]
                
                # 画像デコード（壊れたデータはガードする）
                frame = cv2.imdecode(np.frombuffer(jpg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue

                # --- [ここから画像処理] ---
                # 3. 負荷軽減リサイズ（160x90）
                search_frame = cv2.resize(frame, (160, 90))
                gray = cv2.cvtColor(search_frame, cv2.COLOR_BGR2GRAY)
                gray_blur = cv2.GaussianBlur(gray, (21, 21), 0)

                if avg is None:
                    avg = gray_blur.copy().astype("float")
                    continue

                # 4. 動体検知ロジック
                cv2.accumulateWeighted(gray_blur, avg, LEARNING_RATE)
                frame_delta = cv2.absdiff(gray_blur, cv2.convertScaleAbs(avg))
                thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                max_area = 0
                if contours:
                    max_area = max([cv2.contourArea(c) for c in contours])

                # 5. 録画制御
                current_time = time.time()
                timestamp_str = datetime.now().strftime("%H:%M:%S")

                if max_area > THRESHOLD_AREA:
                    record_until = current_time + EXTEND_SECONDS
                    if not is_recording:
                        cleanup_disk() # 録画開始前に掃除
                        filename = os.path.join(SAVE_DIR, datetime.now().strftime("%Y%m%d_%H%M%S.mp4"))
                        h, w = frame.shape[:2]
                        # 動画保存も10fpsに固定
                        out = cv2.VideoWriter(filename, fourcc, FPS_SETTING, (w, h))
                        is_recording = True
                        print(f"\n[{timestamp_str}] >>> REC START: {filename}")

                if is_recording:
                    out.write(frame)
                    if current_time > record_until:
                        out.release()
                        is_recording = False
                        print(f"\n[{timestamp_str}] <<< REC STOP")

                # ログ表示
                status = "REC" if is_recording else "---"
                print(f"\r[{timestamp_str}] Status: {status} | Area: {max_area:6.0f} ", end="", flush=True)
                
                # フレーム処理が終わったら内部ループを抜けて次のreadへ
                break
            else:
                # 終了合図が見つからない場合はデータが届くのを待つ
                if a == -1 and len(buffer) > 1000000: # 1MB溜まっても開始がないならゴミ
                    buffer = b""
                break

except KeyboardInterrupt:
    print("\nStopping...")
finally:
    if out: out.release()
    proc.terminate()
    print("Resources released.")