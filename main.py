import cv2
import time

print("--- Starting camera with V4L2 backend... ---")

# 【最終奥義】V4L2（Linux専用窓口）を強制指定してカメラを掴む！
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

# 【F3くんのアイデア】Zero 2 Wのフリーズ・処理落ち対策で解像度を下げる
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# カメラの起動と、明るさの自動調整が終わるのを待つ
time.sleep(2)

if not cap.isOpened():
    print("[ERROR] Cannot find the camera.")
else:
    print("Camera opened. Clearing buffer...")
    
    # 【プロの技】最初の5枚は暗かったり不安定なので、シャッターを切って捨てる
    for _ in range(5):
        cap.read()
        time.sleep(0.1)

    # いざ、本命の1枚を撮影！
    ret, frame = cap.read()
    
    if ret:
        # 成功したら画像として保存する
        cv2.imwrite("test_shot.jpg", frame)
        print("[SUCCESS] Camera is working! Saved 'test_shot.jpg'")
    else:
        # まだ空っぽの場合はここに来る
        print("[ERROR] Camera is found, but the picture is STILL black/empty.")

# ゾンビ化を防ぐため、カメラを解放する（お片付け）
cap.release()
print("--- Finished ---")