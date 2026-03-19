import subprocess
import time
import os

# --- [設定] ---
FILENAME = "gpu_test.mp4" # 保存するファイル名
RECORD_SECONDS = 10       # 録画する時間（秒）

# もし古いファイルがあったら消しておく
if os.path.exists(FILENAME):
    os.remove(FILENAME)

# --- [rpicam-vid コマンド] ---
# OpenCVを通さず、直接ファイル(-o)に書き出すので爆速・低負荷です。
cmd = [
    "rpicam-vid",
    "-t", str(RECORD_SECONDS * 1000), # ミリ秒指定
    "--inline",          # 再生互換性のためのヘッダ挿入
    "-o", FILENAME,      # ★直接ファイルに保存！
    "--width", "1920",   # フルHD
    "--height", "1080",
    "--framerate", "30", # 30fps
    "--codec", "h264",   # ★GPU（ハードウェアエンコーダ）を使用
    "--nopreview"        # 画面表示なし（負荷軽減）
]

print(f"=== GPU録画テスト開始 ({RECORD_SECONDS}秒間) ===")
print(f"保存先: {FILENAME}")
print("実行中... (キーボード操作は不要です)")

try:
    # コマンドを実行して、終わるまで待つ
    # Pythonは単にコマンドが終わるのを待つだけなのでCPU負荷はほぼ0です。
    subprocess.run(cmd, check=True)
    
    print("=== 録画完了！ ===")
    
    # ファイルができたか確認
    if os.path.exists(FILENAME):
        size = os.path.getsize(FILENAME) / (1024 * 1024) # MB単位
        print(f"ファイルが正常に作成されました: {FILENAME} ({size:.1f} MB)")
    else:
        print("エラー: ファイルが作成されませんでした。")

except subprocess.CalledProcessError as e:
    print(f"\nエラーが発生しました。カメラが接続されているか確認してください。")
    print(f"コマンドのエラー内容: {e}")
except KeyboardInterrupt:
    print("\n中断されました。")