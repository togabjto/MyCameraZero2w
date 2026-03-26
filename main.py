import cv2
import time

print("--- Starting camera... Please wait ---")

# カメラを掴む
cap = cv2.VideoCapture(0)

# 【超重要】カメラが明るさを調整するまで2秒待つ
time.sleep(2)

if not cap.isOpened():
    print("[ERROR] Cannot find the camera! Check the cable.")
else:
    # 1枚だけ映像を読み込む
    ret, frame = cap.read()
    
    if ret:
        # 画像として保存する
        cv2.imwrite("test_shot.jpg", frame)
        print("[SUCCESS] Camera is working! Saved 'test_shot.jpg'")
    else:
        print("[ERROR] Camera is found, but the picture is black/empty.")

# カメラを解放する
cap.release()