import cv2

print("--- カメラを起動中... ちょっと待ってね ---")

# カメラを掴む（Legacyモードなので0番）
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("【失敗】カメラが見つからない！ケーブルの接続を確認してみて。")
else:
    # 1枚だけ映像を読み込む
    ret, frame = cap.read()
    
    if ret:
        # 画像として保存する
        cv2.imwrite("test_shot.jpg", frame)
        print("【大成功】カメラ動いてるぜ！ 'test_shot.jpg' を保存したよ！")
    else:
        print("【失敗】カメラはいるけど、映像が真っ暗で読み込めない…。")

# カメラを解放する
cap.release()