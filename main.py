import cv2
from flask import Flask, Response

app = Flask(__name__)
# カメラの解像度を落としてメモリを節約 (Zero 2W用)
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

def generate_frames():
    while True:
        success, frame = cap.read()
        if not success:
            break
        else:
            # 画像をJPEGに圧縮
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            # ブラウザに連続して送りつける（MJPEG形式）
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    # 5000番ポートで配信開始！
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)