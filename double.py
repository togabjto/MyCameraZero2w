import cv2
import time
import ctypes
import numpy as np
from numpy.ctypeslib import ndpointer
from picamera2 import Picamera2

# ==========================================
# 1. C言語ライブラリの読み込み
# ==========================================
lib = ctypes.CDLL('./libmotion.so')
lib.detect_motion.argtypes = [ndpointer(ctypes.c_uint8, flags="C_CONTIGUOUS"), ctypes.c_int, ctypes.c_int]
lib.detect_motion.restype = ctypes.c_int

# ==========================================
# 2. Picamera2の準備（OpenCVの代わりにカメラを叩く！）
# ==========================================
picam2 = Picamera2()
# main=録画用(VGAサイズで軽く), lores=動体検知用(さらに軽く)
config = picam2.create_video_configuration(
    main={"size": (640, 480), "format": "RGB888"},
    lores={"size": (320, 240), "format": "YUV420"}
)
picam2.configure(config)
picam2.start()

print("カメラの露出調整中...")
time.sleep(2)

# ==========================================
# 3. OpenCVの録画準備（絶対に失敗しない MJPG の AVI）
# ==========================================
width = 640
height = 480
fps = 15.0
fourcc = cv2.VideoWriter_fourcc(*'MJPG')
out = cv2.VideoWriter('test_record.avi', fourcc, fps, (width, height))

print(f"録画を開始します... (AVI形式, {width}x{height})")
start_time = time.time()

# ==========================================
# 4. メインループ
# ==========================================
while (time.time() - start_time) < 10.0:
    current_sec = time.time() - start_time
    
    # 🌟 Picamera2から確実に綺麗な映像をもらう！
    frame_rgb = picam2.capture_array("main")
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR) # OpenCV用に色を並べ替え

    # 🌟 動体検知用の白黒映像もPicamera2からもらう
    lores_yuv = picam2.capture_array("lores")
    gray_frame = lores_yuv[:240, :320].copy()
    
    # C言語でエラーが出ないように配列を整える（念のため）
    gray_frame_c = np.ascontiguousarray(gray_frame)

    # C言語ライブラリで動体検知！
    is_moving = lib.detect_motion(gray_frame_c, 320, 240)

    if is_moving == 1:
        # 映像そのものに赤い文字を直接書き込む
        cv2.putText(frame_bgr, "Motion Detected!", (20, height - 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        
        # ターミナルにログを表示する
        print(f"[{current_sec:.1f}秒] 動体検知しました！")

    # 文字入りの映像をAVI(MJPG)に書き込む
    out.write(frame_bgr)
    
    # 処理が早すぎないように少し待つ
    time.sleep(1.0 / fps)

# ==========================================
# 5. お片付け
# ==========================================
picam2.stop()
out.release()
print("録画完了！ test_record.avi を保存しました。")