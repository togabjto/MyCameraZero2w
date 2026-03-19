import subprocess
import datetime
import os

def take_still_image():
    # 保存先のディレクトリを作成（なければ）
    save_dir = "/home/pi/Pictures"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # ファイル名に日時を入れる（重複防止）
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{save_dir}/image_{timestamp}.jpg"

    print(f"撮影を開始します: {filename}")

    try:
        # libcamera-still コマンドを呼び出して撮影
        # --immediate: プレビューを待たずに即撮影
        # --nopreview: 画面にプレビューを出さない（ヘッドレス運用向け）
        subprocess.run(["libcamera-still", "-o", filename, "--immediate", "--nopreview"], check=True)
        print("撮影に成功しました！")
        
    except subprocess.CalledProcessError as e:
        print(f"エラーが発生しました。カメラが正しく接続されているか確認してください: {e}")

if __name__ == "__main__":
    take_still_image()