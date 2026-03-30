import cv2
import time
import ctypes
import numpy as np
from numpy.ctypeslib import ndpointer

# ==========================================
# 1. C言語のライブラリを読み込む
# ==========================================
lib = ctypes.CDLL('./libmotion.so') # 先ほど作ったライブラリを指定

# C言語の関数「detect_motion」の引数と戻り値の型を定義
lib.detect_motion.argtypes = [ndpointer(ctypes.c_uint8, flags="C_CONTIGUOUS"), ctypes.c_int, ctypes.c_int]
lib.detect_motion.restype = ctypes.c_int

# ==========================================
# 2. カメラと録画の準備
# ==========================================
cap = cv2.VideoCapture(0) # カメラ起動
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = 10.0 # フレームレート

# H.264やMP4ではなく、ラズパイと相性の良い XVID と .avi に変更！
fourcc = cv2.VideoWriter_fourcc(*'XVID')
out = cv2.VideoWriter('test_record.avi', fourcc, fps, (width, height))

print("録画を開始します（10秒間）...")

start_time = time.time()

# ==========================================
# 3. メインループ（10秒間繰り返す）
# ==========================================
while (time.time() - start_time) < 10.0:
    ret, frame = cap.read()
    if not ret:
        break

    # C言語の動体検知用に、画像を白黒にしてサイズを小さくする（負荷軽減）
    # ※計算用に小さくするだけで、録画自体は元の高画質なframeを使います
    small_frame = cv2.resize(frame, (320, 240))
    gray_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)

    # C言語のライブラリを呼び出して動体検知！
    # 戻り値が1なら検知、0なら未検知
    is_moving = lib.detect_motion(gray_frame, 320, 240)

    # もし動体を検知していたら、映像の右下にテキストを入れる
    if is_moving == 1:
        text = "Motion Detected!"
        # cv2.putText(画像, 文字, 位置(x,y), フォント, サイズ, 色(BGR), 太さ)
        cv2.putText(frame, text, (width - 350, height - 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)

    # テキストが合成された映像を録画ファイルに書き込む
    out.write(frame)

# ==========================================
# 4. お片付け
# ==========================================
cap.release()
out.release()
print("10秒間の録画が完了し、test_record.mp4 を保存しました。")