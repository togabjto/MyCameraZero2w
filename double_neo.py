import time
import ctypes
import numpy as np
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

print("チップを起動中... (監視カメラシステム待機)")
time.sleep(2)

is_recording = False
record_until = 0
filename_base = ""

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
        # 3. CPUの仕事（動体検知ルート）
        # ==========================================
        lores_yuv = picam2.capture_array("lores")
        gray_frame = np.ascontiguousarray(lores_yuv[:240, :320])
        
        # C言語に軽い白黒画像を投げて爆速判定
        is_moving = lib.detect_motion(gray_frame, 320, 240)

        # 動体を検知した場合の処理
        if is_moving == 1:
            # 【重要】録画の終了予定時刻を「今から10秒後」に上書き延長！
            record_until = current_time + 10.0

            if not is_recording:
                # ==========================================
                # 4. GPUの仕事（録画スタート）
                # ==========================================
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename_base = f"record_{timestamp}"
                
                # GPUエンコーダを使ってフルHDのMP4を作成
                encoder = H264Encoder(bitrate=2000000)
                output = FileOutput(f"{filename_base}.mp4")
                picam2.start_recording(encoder, output)
                
                is_recording = True
                record_start_time = current_time
                subtitles = []
                sub_index = 1
                print(f"\n【録画開始】GPUで {filename_base}.mp4 を作成中...")

            # ログ表示と字幕データの作成
            rel_time = current_time - record_start_time
            print(f"[{rel_time:.1f}秒] 動体を検知！（録画を10秒延長）")
            
            start_srt = format_srt_time(rel_time)
            end_srt = format_srt_time(rel_time + 0.5)
            subtitles.append(f"{sub_index}\n{start_srt} --> {end_srt}\n{{\\an3}}Motion Detected!\n\n")
            sub_index += 1

        # ==========================================
        # 5. 録画の停止判定
        # ==========================================
        # 録画中 かつ 最後に動いてから10秒経過したら停止
        if is_recording and current_time > record_until:
            picam2.stop_recording()
            is_recording = False
            
            # 字幕ファイル (.srt) を保存
            with open(f"{filename_base}.srt", "w", encoding="utf-8") as f:
                f.writelines(subtitles)
                
            print(f"【録画停止】10秒間動きがなかったため保存しました。待機モードに戻ります。\n")

        time.sleep(0.05) # CPUを少しだけ休ませる

except KeyboardInterrupt:
    print("\nシステムを終了します。")
finally:
    if is_recording:
        picam2.stop_recording()
        with open(f"{filename_base}.srt", "w", encoding="utf-8") as f:
            f.writelines(subtitles)
    picam2.stop()