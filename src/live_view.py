"""監視（surveillance.py）の中で動く、ライブ映像の配信（オプション）。

検知で使っている 320x240 の白黒フレームを、そのままブラウザへ流す（MJPEG）。
カメラは 1 つのプログラムしか使えないので、監視と同時に見るには、監視の中で配信する必要がある。

- 既定では使わない（surveillance.py に --live-port を付けたときだけ有効）。
- JPEG への変換は、閲覧している接続があるときだけ行う（誰も見ていなければ、フレームの参照を保持するだけ）。
- 映像は個人情報。パスワード必須。通信は HTTP（暗号化されない）なので、LAN の中だけで使う。
- 画質は検知用と同じ（320x240・白黒）。高画質のライブ映像ではない。
- TODO: 閲覧中の CPU・メモリへの影響は未計測。
"""
import io
import json
import os
import sys
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Condition, Thread

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from _auth import is_authorized  # noqa: E402

PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ライブ映像</title>
<style>
body{font-family:sans-serif;max-width:960px;margin:1rem auto;padding:0 1rem}
img{width:100%;background:#000;image-rendering:pixelated}
#st{display:inline-block;padding:.2rem .8rem;border-radius:4px;background:#ddd}
#st.rec{background:#f66;color:#fff}
</style></head><body>
<p>状態: <span id="st">...</span>（320x240・白黒。検知用の映像）</p>
<img src="/stream.mjpg" alt="live">
<script>
async function poll(){
  try{
    const j=await (await fetch('/status')).json();
    const e=document.getElementById('st');
    e.textContent=j.recording?'録画中':'待機中';
    e.className=j.recording?'rec':'';
  }catch(_){document.getElementById('st').textContent='接続できません'}
}
poll();setInterval(poll,1000);
</script></body></html>"""


class LiveView:
    """update() で最新フレームを受け取り、HTTP で MJPEG として配信する。"""

    def __init__(self, host: str, port: int, user: str, password: str, quality: int = 70):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            sys.exit("エラー: ライブ配信には Pillow が必要です（sudo apt install python3-pil）。")
        self.host, self.port = host, port
        self.user, self.password = user, password
        self.quality = quality
        self._cond = Condition()
        self._frame = None
        self._frame_id = 0
        self._frame_time = 0.0
        self._recording = False
        self._ratio = 0.0       # 直近のフレームで「変化した画素」が占める割合（0〜1）。メーター表示用
        self._recent = deque()  # 直近 1 秒の (時刻, 割合)。短い spike を、取得の間隔で見逃さないため
        self.thresholds = {}    # しきい値（pixel_threshold, change_ratio）。メーターの線を引くため、呼び出し側が設定する
        self._pending = None    # 外から届いた、まだ適用していない新しいしきい値 (pixel, ratio)
        self._server = None

    # ---- 監視ループから呼ぶ ----
    def update(self, gray_frame, recording: bool, ratio: float = 0.0) -> None:
        """最新の白黒フレーム（2 次元の numpy 配列）、録画中かどうか、変化した画素の割合を渡す。"""
        with self._cond:
            self._frame = gray_frame  # 参照だけ保持する（変換は閲覧中の接続側で行う）
            self._frame_id += 1
            self._frame_time = time.monotonic()
            self._recording = recording
            self._ratio = ratio
            self._recent.append((self._frame_time, ratio))
            while self._recent and self._frame_time - self._recent[0][0] > 1.0:
                self._recent.popleft()
            self._cond.notify_all()

    def take_pending(self):
        """外から届いた新しいしきい値 (pixel, ratio) を 1 回だけ返す（なければ None）。
        C の変数を別スレッドから書き換えないよう、適用は監視ループ側で行う。"""
        with self._cond:
            pending, self._pending = self._pending, None
            return pending

    @staticmethod
    def parse_params(body):
        """しきい値の指定を検証して (pixel, ratio) を返す。不正なら ValueError。"""
        if not isinstance(body, dict):
            raise ValueError("形式が正しくありません。")
        pixel, ratio = body.get("pixel_threshold"), body.get("change_ratio")
        if isinstance(pixel, bool) or not isinstance(pixel, int) or not 0 <= pixel <= 255:
            raise ValueError("pixel_threshold は 0〜255 の整数です。")
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 < ratio <= 1:
            raise ValueError("change_ratio は 0 より大きく 1 以下の数です。")
        return pixel, float(ratio)

    def start(self) -> None:
        view = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "CameraLive"

            def log_message(self, fmt, *args):
                sys.stderr.write("[live] %s - %s\n" % (self.address_string(), fmt % args))

            def _authorized(self) -> bool:
                if is_authorized(self.headers.get("Authorization"), view.user, view.password):
                    return True
                self.send_response(HTTPStatus.UNAUTHORIZED)
                self.send_header("WWW-Authenticate", 'Basic realm="camera live"')
                self.send_header("Content-Length", "0")
                self.end_headers()
                return False

            def do_GET(self):
                if not self._authorized():
                    return
                if self.path == "/":
                    self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
                elif self.path == "/status":
                    with view._cond:
                        now = time.monotonic()
                        peak = max((r for t, r in view._recent if now - t <= 1.0), default=0.0)
                        body = {"recording": view._recording,
                                "frame_age_s": round(now - view._frame_time, 2) if view._frame_id else None,
                                "ratio": round(view._ratio, 5), "ratio_peak": round(peak, 5),
                                "thresholds": view.thresholds}
                    self._send(json.dumps(body).encode(), "application/json")
                elif self.path == "/stream.mjpg":
                    self._stream()
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)

            def do_POST(self):
                """しきい値の変更を受け取る（Web アプリからの中継用。127.0.0.1 のみ・認証あり）。"""
                if not self._authorized():
                    return
                if self.path != "/params":
                    return self.send_error(HTTPStatus.NOT_FOUND)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    if not 0 < n <= 1024:
                        raise ValueError("リクエストの大きさが正しくありません。")
                    params = view.parse_params(json.loads(self.rfile.read(n)))
                except ValueError as e:
                    return self._send(json.dumps({"ok": False, "message": str(e)}, ensure_ascii=False).encode(),
                                      "application/json", HTTPStatus.BAD_REQUEST)
                with view._cond:
                    view._pending = params
                self._send(b'{"ok": true}', "application/json")

            def _send(self, data: bytes, ctype: str, status=HTTPStatus.OK):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def _stream(self):
                from PIL import Image
                self.send_response(HTTPStatus.OK)
                self.send_header("Cache-Control", "no-cache, private")
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
                self.end_headers()
                last_id = 0
                try:
                    while True:
                        with view._cond:
                            # 新しいフレームを待つ（監視が止まっても、接続が残り続けないよう、タイムアウトを付ける）
                            if not view._cond.wait_for(lambda: view._frame_id != last_id, timeout=5):
                                continue
                            frame, last_id = view._frame, view._frame_id
                        buf = io.BytesIO()
                        Image.fromarray(frame).save(buf, "JPEG", quality=view.quality)  # 2 次元の uint8 は白黒（L）になる
                        data = buf.getvalue()
                        self.wfile.write(b"--FRAME\r\n")
                        self.send_header("Content-Type", "image/jpeg")
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                        self.wfile.write(b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass  # ブラウザが閉じられた

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._server.daemon_threads = True
        Thread(target=self._server.serve_forever, daemon=True, name="live-view").start()
        print(f"[LIVE] ライブ映像を配信中: http://{self.host}:{self.port}/  （ユーザー名: {self.user}）", flush=True)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
