import time
import ctypes
import numpy as np
from numpy.ctypeslib import ndpointer
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput

# ==========================================
# 1. C言語のライブラリを読み込む
# ==========================================
lib = ctypes.CDLL('./libmotion.so')
lib.detect_motion.argtypes = [ndpointer(ctypes.c_uint8, flags="C_CONTIGUOUS"), ctypes.c_int, ctypes.c_int]
lib.detect_motion.restype = ctypes.c_int

# ==========================================
# 2. Picamera2の設定 (デュアルストリーム)
# ==========================================
picam2 = Picamera2()
# main=録画用(1080p), lores=動体検知用(320x240の軽い映像)
config = picam2.create_video_configuration(
    main={"size": (1920, 1080), "format": "YUV420"},
    lores={"size": (320, 240), "format": "YUV420"}
)
picam2.configure(config)
picam2.start()

print("カメラの準備中...")
time.sleep(2) # 明るさやピントが合うまで待つ

# ==========================================
# 3. 録画と「字幕」の準備
# ==========================================
# Picamera2のハードウェアエンコーダを使って、完璧なMP4を作る
encoder = H264Encoder(bitrate=2000000)
output = FileOutput("test_record.mp4")

print("10秒間の録画（Picamera2 1080p MP4）を開始します...")
picam2.start_recording(encoder, output)

start_time = time.time()

# 字幕データ保存用
subtitles = []
sub_index = 1

# 字幕の時間を計算する便利関数
def format_srt_time(seconds):
    ms = int((seconds % 1) * 1000)
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

# ==========================================
# 4. メインループ（10秒間監視）
# ==========================================
while (time.time() - start_time) < 10.0:
    current_sec = time.time() - start_time

    # 【超エコロジー】OpenCVを使わず、YUVデータの「Y(明るさ=白黒)」成分だけを直接抜き取る！
    lores_yuv = picam2.capture_array("lores")
    gray_frame = lores_yuv[:240, :320].copy() 

    # C言語のライブラリに白黒画像を渡して動体検知
    is_moving = lib.detect_motion(gray_frame, 320, 240)

    if is_moving == 1:
        print(f"[{current_sec:.1f}秒] 動体検知！")
        
        # 検知した瞬間の時間を記録し、字幕データを作る（0.5秒間表示）
        start_srt = format_srt_time(current_sec)
        end_srt = format_srt_time(current_sec + 0.5)
        
        # {\an3} は「画面右下」に字幕を配置する mpv のコマンドです
        subtitles.append(f"{sub_index}\n{start_srt} --> {end_srt}\n{{\\an3}}動体検知しました\n\n")
        sub_index += 1

    time.sleep(0.1) # CPUを休ませる

# ==========================================
# 5. お片付けと字幕ファイルの作成
# ==========================================
picam2.stop_recording()
picam2.stop()

# 字幕ファイル (.srt) を作成して保存
with open("test_record.srt", "w", encoding="utf-8") as f:
    f.writelines(subtitles)

print("録画完了！ test_record.mp4 と test_record.srt を保存しました。")