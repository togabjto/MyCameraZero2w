import cv2
import time
import ctypes
import numpy as np
from numpy.ctypeslib import ndpointer

# 1. C言語ライブラリの読み込み
lib = ctypes.CDLL('./libmotion.so')
lib.detect_motion.argtypes = [ndpointer(ctypes.c_uint8, flags="C_CONTIGUOUS"), ctypes.c_int, ctypes.c_int]
lib.detect_motion.restype = ctypes.c_int

# 2. カメラの準備 (V4L2モードで直接叩くことでさらに軽くする)
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

# 解像度を 640x480 (VGA) に設定。AVIは容量が大きくなるのでこのサイズが最適！
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 15) # 15fpsあれば監視カメラとして十分滑らか

if not cap.isOpened():
    print("カメラが開けません。'sudo pkill python3' を試してください。")
    exit()

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = 15.0

# ★ここがドラレコ方式！ MP4を捨てて、軽くて頑丈な AVI (XVID) にする
fourcc = cv2.VideoWriter_fourcc(*'XVID')
out = cv2.VideoWriter('test_record.avi', fourcc, fps, (width, height))

print(f"録画を開始します... (AVI形式, {width}x{height})")
start_time = time.time()

# 3. メインループ
while (time.time() - start_time) < 10.0:
    ret, frame = cap.read()
    if not ret:
        continue

    # 動体検知用に白黒＆縮小 (C言語に渡す用)
    small_frame = cv2.resize(frame, (320, 240))
    gray_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)

    # C言語ライブラリで判定 (爆速)
    is_moving = lib.detect_motion(gray_frame, 320, 240)

    # 動いていたら、映像そのものに文字を焼き込む！
    if is_moving == 1:
        cv2.putText(frame, "Motion Detected!", (20, height - 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

    # 文字が入った(または入ってない)フレームをAVIファイルに書き込む
    # XVIDアルゴリズムは軽いのでサクサク進む
    out.write(frame)

# 4. 終了処理
cap.release()
out.release()
print("録画完了！ test_record.avi を保存しました。")