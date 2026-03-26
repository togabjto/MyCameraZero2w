import cv2
import time

print("--- Starting camera with low resolution ---")

cap = cv2.VideoCapture(0)

# 【ここがF3くんのアイデア！】解像度を640x480に下げる
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# カメラの起動を待つ
time.sleep(2)

if not cap.isOpened():
    print("[ERROR] Cannot find the camera.")
else:
    print("Camera opened. Clearing buffer...")
    
    # 【プロの技】最初の5フレームは暗かったり不安定なので、読み込んで捨てる
    for _ in range(5):
        cap.read()
        time.sleep(0.1)

    # いざ、本命の1枚を撮影！
    ret, frame = cap.read()
    
    if ret:
        cv2.imwrite("test_shot.jpg", frame)
        print("[SUCCESS] Camera is working! Saved 'test_shot.jpg'")
    else:
        print("[ERROR] Camera is found, but the picture is STILL black/empty.")

cap.release()