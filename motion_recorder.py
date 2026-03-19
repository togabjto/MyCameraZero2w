import time
import os
import numpy as np
import cv2
from datetime import datetime
from picamera2 import Picamera2
from picamera2.outputs import CircularOutput

# --- [Settings] ---
SAVE_DIR = "movie"
PRE_RECORD_SECONDS = 5  # 過去何秒分を保持するか（Zero 2 Wなら5〜10秒が限界）
POST_RECORD_SECONDS = 5 # 検知後、さらに何秒撮るか
THRESHOLD_AREA = 100    # 160x90用の感度
LEARNING_RATE = 0.05

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# 1. Picamera2の初期化
picam2 = Picamera2()

# 2. マルチストリーム設定（メイン：録画用、ロレス：解析用）
# ロレス(lores)を160x90にすることで、CPU負荷を最小限に抑えます
config = picam2.create_video_configuration(
    main={"size": (1280, 720), "format": "H264", "fps": 10},
    lores={"size": (160, 90), "format": "YUV420", "fps": 10}
)
picam2.configure(config)
picam2.start()

# 3. 循環バッファ（メモリ上のバケツ）の準備
# H.264形式で、指定した秒数分だけメモリに溜め続けます
circ_output = CircularOutput(PRE_RECORD_SECONDS, format="h264")
picam2.start_recording(circ_output)

print(f"--- Dashcam Mode Online (Pre-record: {PRE_RECORD_SECONDS}s) ---")

avg = None
is_recording = False
record_until = 0



try:
    while True:
        # 4. 「おこぼれ」の低解像度データを取得（解析用）
        # capture_arrayは、現在の最新フレームをnumpy配列として一瞬で取ってきます
        lores_frame = picam2.capture_array("lores")
        
        # YUV420形式のデータから輝度(Y)チャンネルだけ抜き出し（＝グレースケール）
        gray = lores_frame[:, :, 0]
        gray_blur = cv2.GaussianBlur(gray, (21, 21), 0)

        if avg is None:
            avg = gray_blur.copy().astype("float")
            continue

        # 5. 動体検知ロジック
        cv2.accumulateWeighted(gray_blur, avg, LEARNING_RATE)
        frame_delta = cv2.absdiff(gray_blur, cv2.convertScaleAbs(avg))
        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        max_area = 0
        if contours:
            max_area = max([cv2.contourArea(c) for c in contours])

        # 6. 検知と保存（ドラレコ方式の核心）
        current_time = time.time()
        if max_area > THRESHOLD_AREA:
            record_until = current_time + POST_RECORD_SECONDS
            if not is_recording:
                filename = os.path.join(SAVE_DIR, datetime.now().strftime("%Y%m%d_%H%M%S_event.mp4"))
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] >>> 動き検知！過去{PRE_RECORD_SECONDS}秒を含めて保存開始")
                is_recording = True

        if is_recording:
            if current_time > record_until:
                # バッファの中身をファイルに書き出す
                # これにより「過去＋現在」が1つの動画になります
                circ_output.save(filename)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] <<< 保存完了: {filename}")
                is_recording = False

        print(f"\rMonitoring... Area: {max_area:6.0f} ", end="", flush=True)
        time.sleep(0.1) # 10fps程度に抑えてCPUを休ませる

except KeyboardInterrupt:
    print("\nStopping...")
finally:
    picam2.stop_recording()
    picam2.stop()