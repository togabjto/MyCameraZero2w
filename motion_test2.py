import cv2
import numpy as np
import subprocess
import time
from datetime import datetime

# --- [Settings] ---
THRESHOLD_AREA = 500  # 更新が速くなるので、感度は少し下げ目（数値を大きく）から調整
LEARNING_RATE = 0.1   # FPSが上がるので、背景学習も少し速めに設定

# 1. 起動時にカメラプロセスを一本立ち上げる (動画モード)
# --inline: 各フレームにヘッダーを含める
# --codec mjpeg: OpenCVでデコードしやすい形式
cmd = [
    "rpicam-vid", "-t", "0", "--inline", "-o", "-", 
    "--width", "320", "--height", "240", "--nopreview", 
    "--framerate", "20", "--codec", "mjpeg"
]

# プロセスを開始
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**6)

avg = None
is_detecting = False

print("--- High-Speed Video Stream Mode ---")
print(" Press [Ctrl+C] to stop")

try:
    buffer = b""
    while True:
        # 2. MJPEGストリームから1枚のJPG画像を切り出すロジック
        # 標準出力からデータを読み込む
        buffer += proc.stdout.read(4096)
        a = buffer.find(b'\xff\xd8') # JPEGの開始バイナリ
        b = buffer.find(b'\xff\xd9') # JPEGの終了バイナリ
        
        if a != -1 and b != -1:
            jpg_data = buffer[a:b+2]
            buffer = buffer[b+2:]
            
            # バイナリをOpenCV形式の画像にデコード
            frame = cv2.imdecode(np.frombuffer(jpg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue

            # --- [Motion Detection Logic] ---
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray_blur = cv2.GaussianBlur(gray, (21, 21), 0)

            if avg is None:
                print("\nBackground model initialized.")
                avg = gray_blur.copy().astype("float")
                continue

            # 背景更新と差分計算
            cv2.accumulateWeighted(gray_blur, avg, LEARNING_RATE)
            frame_delta = cv2.absdiff(gray_blur, cv2.convertScaleAbs(avg))
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            max_area = 0
            if contours:
                max_area = max([cv2.contourArea(c) for c in contours])

            # --- [Real-time Log Output] ---
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-4] # コンマ秒まで
            
            if max_area > THRESHOLD_AREA:
                status = " [!] MOTION "
                if not is_detecting:
                    print(f"\n[{timestamp}] >>> DETECTED") # 検知開始時だけ改行
                is_detecting = True
            else:
                status = " [-] Watch... "
                if is_detecting:
                    print(f"\n[{timestamp}] <<< STOPPED") # 停止時だけ改行
                is_detecting = False

            # \r で常に同じ行を上書き更新
            print(f"\r[{timestamp}]{status}| Area: {max_area:6.0f} ", end="", flush=True)

except KeyboardInterrupt:
    print("\nStopping stream...")
finally:
    proc.terminate() # カメラプロセスを終了
    print("Camera released.")