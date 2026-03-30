import os
import glob
import time
import ctypes
import numpy as np
import subprocess
from numpy.ctypeslib import ndpointer
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput

# ==========================================
# 1. 保存先ディレクトリと通し番号の準備
# ==========================================
MOVIE_DIR = "movie"
os.makedirs(MOVIE_DIR, exist_ok=True) # movieディレクトリが無ければ作る

def get_next_file_number():
    """movieディレクトリ内を調べて、次の通し番号を返す"""
    files = glob.glob(os.path.join(MOVIE_DIR, "*.mp4"))
    max_num = 0
    for f in files:
        basename = os.path.basename(f)
        name, ext = os.path.splitext(basename)
        if name.isdigit():
            num = int(name)
            if num > max_num:
                max_num = num
    return max_num + 1

# ==========================================
# 2. C言語ライブラリの読み込み
# ==========================================
lib = ctypes.CDLL('./libmotion.so')
lib.detect_motion.argtypes = [ndpointer(ctypes.c_uint8, flags="C_CONTIGUOUS"), ctypes.c_int, ctypes.c_int]
lib.detect_motion.restype = ctypes.c_int

# ==========================================
# 3. カメラと分岐チップの設定
# ==========================================
picam2 = Picamera2()
config = picam2.create_video_configuration(
    main={"size": (1920, 1080), "format": "YUV420"}, # GPU録画用 (フルHD)
    lores={"size": (320, 240), "format": "YUV420"}   # CPU検知用 (低解像度)
)
picam2.configure(config)
picam2.start()

print("監視カメラシステム起動...")
print(f"保存先: {os.path.abspath(MOVIE_DIR)}/\n")
time.sleep(2)

is_recording = False
record_until = 0
temp_filename = "temp_raw.h264" # 梱包前の一時データ
current_file_num = 0

try:
    while True:
        current_time = time.time()

        # ==========================================
        # 4. 動体検知の処理
        # ==========================================
        lores_yuv = picam2.capture_array("lores")
        gray_frame = np.ascontiguousarray(lores_yuv[:240, :320])
        
        is_moving = lib.detect_motion(gray_frame, 320, 240)

        if is_moving == 1:
            # 【重要】動くたびに録画終了予定時刻を「今から10秒後」に延長(上書き)する！
            record_until = current_time + 10.0

            if not is_recording:
                # 録画していない時だけ新規スタート
                current_file_num = get_next_file_number()
                # 4桁のゼロ埋め番号にする (例: 0001, 0002)
                filename_base = f"{current_file_num:04d}" 
                
                print(f"【検知】動体検知！ {filename_base}.mp4 の録画を開始します。")
                
                encoder = H264Encoder(bitrate=2000000)
                output = FileOutput(temp_filename)
                picam2.start_recording(encoder, output)
                
                is_recording = True
            else:
                # 録画中の場合は延長を知らせる（ログがうるさければ消してOK）
                print(f"  -> 動きを継続検知（録画時間を10秒延長）")

        # ==========================================
        # 5. 録画の停止 ＆ MP4変換処理
        # ==========================================
        # 録画中 かつ 最後に動いてから10秒経過したら停止
        if is_recording and current_time >= record_until:
            picam2.stop_recording()
            is_recording = False
            
            final_mp4 = os.path.join(MOVIE_DIR, f"{current_file_num:04d}.mp4")
            print(f"【停止】10秒間動きがなかったため停止しました。MP4に変換中...")
            
            # むき出しのH.264を、QuickTimeでも再生できるMP4に梱包する
            subprocess.run(["ffmpeg", "-y", "-framerate", "30", "-i", temp_filename, "-c", "copy", final_mp4], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 一時ファイルを消す
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
                
            print(f"【保存完了】 {final_mp4} を保存しました。待機モードに戻ります。\n")

        time.sleep(0.05) # CPUを休ませる

except KeyboardInterrupt:
    print("\nシステムを強制終了します。")
finally:
    # 途中で Ctrl+C を押された場合のお片付け
    if is_recording:
        picam2.stop_recording()
        if os.path.exists(temp_filename):
            os.remove(temp_filename) # 中途半端な一時ファイルは消す
    picam2.stop()
    print("終了しました。")