import cv2
import time
import ctypes
import numpy as np
from numpy.ctypeslib import ndpointer

# ==========================================
# 1. C言語ライブラリの読み込み
# ==========================================
lib = ctypes.CDLL('./libmotion.so')
lib.detect_motion.argtypes = [ndpointer(ctypes.c_uint8, flags="C_CONTIGUOUS"), ctypes.c_int, ctypes.c_int]
lib.detect_motion.restype = ctypes.c_int

# ==========================================
# 2. カメラの準備
# ==========================================
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

# 負荷を抑えるため VGA(640x480) 15fps に設定
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 15)

if not cap.isOpened():
    print("【エラー】カメラが開けません。'sudo pkill python3' を試してください。")
    exit()

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = 15.0

# ★ MP4ではなく、軽くて安全な AVI (XVID) に変更
fourcc = cv2.VideoWriter_fourcc(*'XVID')
out = cv2.VideoWriter('test_record.avi', fourcc, fps, (width, height))

print(f"録画を開始します... (AVI形式, {width}x{height})")
start_time = time.time()

# ==========================================
# 3. メインループ
# ==========================================
while (time.time() - start_time) < 10.0:
    current_sec = time.time() - start_time
    
    ret, frame = cap.read()
    if not ret:
        continue

    # C言語で動体検知するための下準備（白黒＆縮小）
    small_frame = cv2.resize(frame, (320, 240))
    gray_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)

    # C言語ライブラリに投げて判定
    is_moving = lib.detect_motion(gray_frame, 320, 240)

    if is_moving == 1:
        # ① 映像そのものに赤い文字を直接書き込む
        cv2.putText(frame, "Motion Detected!", (20, height - 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        
        # ② ターミナルにログを表示する（復活！）
        print(f"[{current_sec:.1f}秒] 動体検知しました！")

    # 文字入り(または文字なし)の映像をAVIに書き込む
    out.write(frame)

# ==========================================
# 4. お片付け
# ==========================================
cap.release()
out.release()
print("録画完了！ test_record.avi を保存しました。")