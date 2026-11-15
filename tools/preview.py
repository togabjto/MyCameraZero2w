"""カメラ設置時の画角確認（ライブ映像・デバッグ用）。

カメラの映像を MJPEG でブラウザに流す。

重要: 監視（src/surveillance.py）と同時には使えない。
      カメラは 1 つのプログラムしか使えないため、先に監視を止めてから起動する。
      カメラが使用中なら、その旨を表示して終了する。

使い方:
    TOOLS_PASSWORD=xxxx python3 tools/preview.py
    → 同じ LAN のブラウザで http://<Pi の IP>:8001/ を開く
    確認が終わったら Ctrl+C で止めて、監視を再開する。

方針:
- 映像は個人情報。パスワード必須。LAN の中だけで使う（HTTP なので暗号化されない）。
- TODO: 実機での負荷（CPU・メモリ）は未計測。
"""
import argparse
import io
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Condition

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _auth import add_common_args, is_authorized, require_password  # noqa: E402

PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>画角の確認</title>
<style>
body{font-family:sans-serif;max-width:960px;margin:1rem auto;padding:0 1rem}
img{width:100%;background:#000}
.warn{background:#ffe9a8;padding:.6rem 1rem;border-radius:4px}
</style></head><body>
<p class="warn">監視は停止中です。画角の確認が終わったら、Pi で Ctrl+C を押して、監視を再開してください。</p>
<img src="/stream.mjpg" alt="camera">
</body></html>"""


class StreamingOutput(io.BufferedIOBase):
    """エンコーダから届いた最新のフレームを保持し、待っている接続へ知らせる。"""

    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = bytes(buf)
            self.condition.notify_all()
        return len(buf)


class Handler(BaseHTTPRequestHandler):
    server_version = "CameraPreview"
    output: StreamingOutput = None
    user = "admin"
    password = ""

    def log_message(self, fmt, *args):
        sys.stderr.write("[preview] %s - %s\n" % (self.address_string(), fmt % args))

    def _authorized(self) -> bool:
        if is_authorized(self.headers.get("Authorization"), self.user, self.password):
            return True
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="camera tools"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):
        if not self._authorized():
            return
        if self.path == "/":
            data = PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/stream.mjpg":
            self._stream()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _stream(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Age", "0")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
        self.end_headers()
        try:
            while True:
                with self.output.condition:
                    self.output.condition.wait()
                    frame = self.output.frame
                self.wfile.write(b"--FRAME\r\n")
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass  # ブラウザが閉じられた


def main():
    parser = argparse.ArgumentParser(description="カメラの画角確認（デバッグ用）")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=10, help="配信のフレームレート（既定: 10）")
    add_common_args(parser)
    parser.set_defaults(port=8001)
    args = parser.parse_args()
    require_password(args)

    # picamera2 は Pi 以外では入っていないので、ここで読み込む
    from picamera2 import Picamera2
    from picamera2.encoders import MJPEGEncoder
    from picamera2.outputs import FileOutput

    try:
        picam2 = Picamera2()
    except Exception as e:  # 使用中・未接続など
        sys.exit(
            "エラー: カメラを開けません。src/surveillance.py が動いていないか確認してください"
            f"（カメラは同時に 1 つのプログラムしか使えません）。\n詳細: {e}"
        )

    output = StreamingOutput()
    try:
        config = picam2.create_video_configuration(
            main={"size": (args.width, args.height)},
            controls={"FrameRate": args.fps},
        )
        picam2.configure(config)
        picam2.start_recording(MJPEGEncoder(), FileOutput(output))
    except Exception as e:
        picam2.close()
        sys.exit(f"エラー: カメラを開始できません。\n詳細: {e}")

    Handler.output = output
    Handler.user = args.user
    Handler.password = args.password
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[preview] 配信中: http://{args.host}:{args.port}/  （Ctrl+C で終了）", flush=True)
    print("[preview] 注意: 監視は止まっています。確認が終わったら Ctrl+C で止めて、監視を再開してください。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[preview] 終了します。")
    finally:
        server.server_close()
        picam2.stop_recording()
        picam2.close()


if __name__ == "__main__":
    main()
