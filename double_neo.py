import time
import ctypes
import numpy as np
import subprocess
import os
from datetime import datetime
from numpy.ctypeslib import ndpointer
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput

# ==========================================
# 1. C言語ライブラリの読み込み
# ==========================================
lib = ctypes.CDLL('./libmotion.so')
lib.detect_motion.argtypes = [ndpointer(ctypes.c_uint8, flags="C_CONTIGUOUS"), ctypes.c_int, ctypes.c_int]
lib.detect_motion.restype = ctypes.c_int

# ==========================================
# 2. 分岐チップ（ISP）の設定：データを2つに分ける
# ==========================================
picam2 = Picamera2()
config = picam2.create_video_configuration(
    main={"size": (1920, 1080), "format": "YUV420"}, # GPU録画用（フルHD）
    lores={"size": (320, 240), "format": "YUV420"}   # CPU検知用（低解像度）
)
picam2.configure(config)
picam2.start()

print("カメラとチップを起動中... (10秒スッパリ録画モード)")
time.sleep(2)

is_recording = False
record_end_time = 0
temp_filename = "temp_raw.h264" # 一時保存用のむき出しデータ
final_filename = ""

# 字幕用変数
subtitles = []
sub_index = 1
record_start_time = 0

def format_srt_time(seconds):
    ms = int((seconds % 1) * 1000)
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

try:
    while True:
        current_time = time.time()

        # ==========================================
        # 3. 動体検知の処理
        # ==========================================
        lores_yuv = picam2.capture_array("lores")
        gray_frame = np.ascontiguousarray(lores_yuv[:240, :320])
        
        is_moving = lib.detect_motion(gray_frame, 320, 240)

        # 動体を検知した場合
        if is_moving == 1:
            if not is_recording:
                # 録画していない時だけ、新規スタート（延長はしない）
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                final_filename = f"record_{timestamp}"
                
                # GPUエンコーダを使ってフルHDの「むき出しデータ」を作成
                encoder = H264Encoder(bitrate=2000000)
                output = FileOutput(temp_filename)
                picam2.start_recording(encoder, output)
                
                is_recording = True
                record_start_time = current_time
                record_end_time = current_time + 10.0 # 録画終了を「ピッタリ10秒後」に固定
                
                subtitles = []
                sub_index = 1
                print(f"\n【検知】録画スタート！10秒間記録します...")

            # 録画中なら、検知した瞬間のログと字幕データだけ作る
            if is_recording:
                rel_time = current_time - record_start_time
                print(f"[{rel_time:.1f}秒] 動体を検知！")
                
                start_srt = format_srt_time(rel_time)
                end_srt = format_srt_time(rel_time + 0.5)
                subtitles.append(f"{sub_index}\n{start_srt} --> {end_srt}\n{{\\an3}}Motion Detected!\n\n")
                sub_index += 1

        # ==========================================
        # 4. スッパリ10秒で停止 ＆ MP4の箱詰め処理
        # ==========================================
        if is_recording and current_time >= record_end_time:
            picam2.stop_recording()
            is_recording = False
            print("【停止】10秒経過したため録画を停止しました。動画を梱包しています...")
            
            # むき出しのH.264を、QuickTimeで見られる正しいMP4の箱に詰め替える（爆速で終わります）
            mp4_file = f"{final_filename}.mp4"
            subprocess.run(["ffmpeg", "-y", "-framerate", "30", "-i", temp_filename, "-c", "copy", mp4_file], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 一時ファイルを消す
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
                
            # 字幕ファイル (.srt) を保存
            with open(f"{final_filename}.srt", "w", encoding="utf-8") as f:
                f.writelines(subtitles)
                
            print(f"【保存完了】 {mp4_file} が完成しました。待機モードに戻ります。\n")
            break

        time.sleep(0.05) # CPUを休ませる

except KeyboardInterrupt:
    print("\nシステムを終了します。")
finally:
    if is_recording:
        picam2.stop_recording()
    picam2.stop()