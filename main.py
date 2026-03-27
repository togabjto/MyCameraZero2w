import cv2
print("hello")

# V3カメラをLinux標準窓口(V4L2)で開く
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

# 解像度の設定（V3は高画質すぎるので、最初は低めが安定）
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

ret, frame = cap.read()
if ret:
    cv2.imwrite("v3_capture.jpg", frame)
    print("success！")

cap.release()