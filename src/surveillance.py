import os
import sys
import glob
import argparse
import time
import ctypes
import numpy as np
import subprocess
from numpy.ctypeslib import ndpointer
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput

# ==========================================
# 1. Setup Directory
# ==========================================
MOVIE_DIR = "movie"
os.makedirs(MOVIE_DIR, exist_ok=True)

def get_next_file_number():
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

# 起動時に 1 回だけファイルから初期化し、以後はメモリ上のカウンタで管理する。
# （変換中の MP4 はまだ存在しないため、毎回ファイルを数えると番号が重複しうる）
next_file_number = get_next_file_number()

# ==========================================
# 2. Load C Library
# ==========================================
# スクリプトと同じ場所から読み込む（実行時のカレントディレクトリに依存しない）
LIB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libmotion.so")
lib = ctypes.CDLL(LIB_PATH)
lib.detect_motion.argtypes = [ndpointer(ctypes.c_uint8, flags="C_CONTIGUOUS"), ctypes.c_int, ctypes.c_int]
lib.detect_motion.restype = ctypes.c_int
lib.set_motion_params.argtypes = [ctypes.c_int, ctypes.c_double]
lib.set_motion_params.restype = ctypes.c_int

# 検知のしきい値（既定値は従来と同じ。感度を変えて試すときに指定する）
parser = argparse.ArgumentParser(description="動体検知つき監視カメラ")
parser.add_argument("--pixel-threshold", type=int, default=30,
                    help="画素の変化量のしきい値 0-255（既定: 30）")
parser.add_argument("--change-ratio", type=float, default=0.03,
                    help="変化した画素の割合のしきい値 0〜1（既定: 0.03）")
# ライブ映像の配信（既定は無効。--live-port を付けたときだけ動く）
parser.add_argument("--live-port", type=int, default=0,
                    help="ライブ映像を配信するポート番号（既定: 0 = 配信しない）")
parser.add_argument("--live-host", default="0.0.0.0", help="ライブ映像の待ち受けアドレス（既定: 0.0.0.0）")
parser.add_argument("--live-user", default="admin", help="ライブ映像のユーザー名（既定: admin）")
parser.add_argument("--live-password", default=os.environ.get("TOOLS_PASSWORD"),
                    help="ライブ映像のパスワード（環境変数 TOOLS_PASSWORD でも指定できる。配信するなら必須）")
args = parser.parse_args()
if lib.set_motion_params(args.pixel_threshold, args.change_ratio) != 0:
    sys.exit("エラー: しきい値が範囲外です（--pixel-threshold は 0-255、--change-ratio は 0 より大きく 1 以下）")
print(f"[CONFIG] pixel_threshold={args.pixel_threshold} change_ratio={args.change_ratio}", flush=True)

live = None
if args.live_port:
    if not args.live_password:
        sys.exit("エラー: ライブ配信にはパスワードが必要です（--live-password か環境変数 TOOLS_PASSWORD）。")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 起動のしかたに依存せず、同じ場所の live_view を読む
    from live_view import LiveView
    live = LiveView(args.live_host, args.live_port, args.live_user, args.live_password)

# ==========================================
# 3. Camera Setup
# ==========================================
picam2 = Picamera2()
config = picam2.create_video_configuration(
    main={"size": (1920, 1080), "format": "YUV420"}, 
    lores={"size": (320, 240), "format": "YUV420"}   
)
picam2.configure(config)
picam2.start()

print("\n" + "="*40, flush=True)
print(" SYSTEM READY: Surveillance Camera", flush=True)
print("="*40 + "\n", flush=True)
time.sleep(2)
if live:
    live.start()

is_recording = False
record_until = 0
current_file_num = 0
temp_filename = ""

print("[WAITING] Monitoring for motion...", flush=True)

try:
    while True:
        current_time = time.time()

        # ---------- デバッグログ追加 ----------
        # print("[DEBUG] Getting frame...", flush=True) # ログが多すぎる場合は消してください
        
        # 映像の取得（フリーズするなら絶対ココ！）
        lores_yuv = picam2.capture_array("lores")
        gray_frame = np.ascontiguousarray(lores_yuv[:240, :320])
        
        # print("[DEBUG] Frame OK", flush=True)
        # --------------------------------------

        if live:
            live.update(gray_frame, is_recording)

        is_moving = lib.detect_motion(gray_frame, 320, 240)

        if is_moving == 1:
            record_until = current_time + 10.0

            if not is_recording:
                current_file_num = next_file_number
                next_file_number += 1
                filename_base = f"{current_file_num:04d}" 
                temp_filename = f"temp_{filename_base}.h264"
                
                print(f"\n[DETECTED] Motion! Starting record: {filename_base}.mp4", flush=True)
                print("[DEBUG] Starting encoder...", flush=True)
                
                # エンコーダを毎回新鮮な状態で作成
                encoder = H264Encoder(bitrate=2000000)
                output = FileOutput(temp_filename)
                picam2.start_recording(encoder, output)
                is_recording = True
                
                print("[DEBUG] Record is running.", flush=True)

        # ==========================================
        # 4. Stop Recording & Force Camera Reset
        # ==========================================
        if is_recording and current_time >= record_until:
            print(f"[STOP] No motion for 10s. Stopping record...", flush=True)
            picam2.stop_recording()
            is_recording = False
            
            # 🌟【究極の対策】カメラのパニックを治すため、一度完全にシャットダウンして再起動する
            print("[DEBUG] Resetting camera pipeline to prevent freeze...", flush=True)
            picam2.stop()      # カメラのメモリを完全解放！
            time.sleep(0.5)    # 息継ぎ
            picam2.start()     # 綺麗な状態で再起動！
            print("[DEBUG] Camera reset COMPLETE.", flush=True)
            
            # 裏方でMP4に変換
            final_mp4 = os.path.join(MOVIE_DIR, f"{current_file_num:04d}.mp4")
            print(f"[CONVERT] Converting to MP4 in background...", flush=True)
            cmd = f"ffmpeg -y -framerate 30 -i {temp_filename} -c copy {final_mp4} && rm {temp_filename}"
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            print("-" * 40, flush=True)
            print("[WAITING] Resuming motion detection...", flush=True)
            print("-" * 40 + "\n", flush=True)

        time.sleep(0.05) 

except KeyboardInterrupt:
    print("\n\n[EXIT] Shutting down system...", flush=True)
finally:
    if is_recording:
        picam2.stop_recording()
    picam2.stop()
    print("[EXIT] Camera safely closed.", flush=True)