"""録画データのビューア（デバッグ用）。

録画フォルダの MP4 を一覧にして、ブラウザで再生する。
再生・一時停止・10 秒とばし・倍速は、ブラウザの <video> を使う。
シーク（10 秒とばし）に必要な Range リクエストに対応している。

使い方:
    TOOLS_PASSWORD=xxxx python3 tools/viewer.py --dir src/movie
    → 同じ LAN のブラウザで http://<Pi の IP>:8000/ を開く

方針:
- 読み取り専用。配るのは --dir 直下の *.mp4 だけ（フォルダ外は配らない）。
- パスワード必須。LAN の中だけで使う（HTTP なので暗号化されない）。
"""
import argparse
import html
import os
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _auth import add_common_args, is_authorized, require_password  # noqa: E402

NAME_RE = re.compile(r"^[A-Za-z0-9_\-]+\.mp4$")
CHUNK = 64 * 1024

PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:sans-serif;max-width:960px;margin:1rem auto;padding:0 1rem}}
video{{width:100%;background:#000}}
button{{font-size:1rem;margin:.2rem;padding:.4rem .8rem}}
li{{margin:.3rem 0}}
</style></head><body>{body}</body></html>"""

WATCH_BODY = """<p><a href="/">&larr; 一覧</a></p>
<h2>{name}</h2>
<video id="v" src="/video/{name}" controls autoplay playsinline></video>
<p>
<button onclick="skip(-10)">-10秒</button>
<button onclick="skip(10)">+10秒</button>
<button onclick="speed(0.5)">0.5x</button>
<button onclick="speed(1)">1x</button>
<button onclick="speed(2)">2x</button>
<button onclick="speed(4)">4x</button>
<button onclick="toggle()">再生/一時停止</button>
</p>
<p>キー: 空白=再生/一時停止, ←/→=10秒戻る/進む</p>
<script>
const v=document.getElementById('v');
function skip(s){{v.currentTime=Math.max(0,v.currentTime+s)}}
function speed(r){{v.playbackRate=r}}
function toggle(){{v.paused?v.play():v.pause()}}
document.addEventListener('keydown',e=>{{
  if(e.key===' '){{e.preventDefault();toggle()}}
  else if(e.key==='ArrowLeft')skip(-10);
  else if(e.key==='ArrowRight')skip(10);
}});
</script>"""


def parse_range(value: str, size: int):
    """'bytes=a-b' を (start, end) にする。不正なら None。end は含む。"""
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return None
    if m.group(1) == "":  # 末尾 N バイト
        n = int(m.group(2))
        if n == 0:
            return None
        return max(0, size - n), size - 1
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else size - 1
    end = min(end, size - 1)
    if start > end or start >= size:
        return None
    return start, end


class Handler(BaseHTTPRequestHandler):
    server_version = "CameraViewer"
    movie_dir = "."
    user = "admin"
    password = ""

    def log_message(self, fmt, *args):  # 標準のログ形式を短くする
        sys.stderr.write("[viewer] %s - %s\n" % (self.address_string(), fmt % args))

    # ---- 共通 ----
    def _authorized(self) -> bool:
        if is_authorized(self.headers.get("Authorization"), self.user, self.password):
            return True
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="camera tools"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def _send_html(self, title: str, body: str, status=HTTPStatus.OK):
        data = PAGE.format(title=html.escape(title), body=body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _not_found(self):
        self._send_html("見つかりません", "<p>見つかりません。</p>", HTTPStatus.NOT_FOUND)

    def _resolve(self, name: str):
        """名前を検証して、録画フォルダ内の実ファイルのパスを返す。なければ None。"""
        name = unquote(name)
        if not NAME_RE.match(name):
            return None
        path = os.path.join(self.movie_dir, name)
        if not os.path.isfile(path):
            return None
        # シンボリックリンクなどでフォルダの外を指していないか確認
        real_dir = os.path.realpath(self.movie_dir)
        if os.path.commonpath([os.path.realpath(path), real_dir]) != real_dir:
            return None
        return path

    # ---- ルーティング ----
    def do_GET(self):
        if not self._authorized():
            return
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._index()
        elif path.startswith("/watch/"):
            self._watch(path[len("/watch/"):])
        elif path.startswith("/video/"):
            self._video(path[len("/video/"):])
        else:
            self._not_found()

    def _index(self):
        try:
            names = sorted(n for n in os.listdir(self.movie_dir) if NAME_RE.match(n))
        except OSError:
            names = []
        items = []
        for n in reversed(names):  # 新しいもの（番号が大きいもの）を上に
            size_mb = os.path.getsize(os.path.join(self.movie_dir, n)) / 1e6
            items.append(f'<li><a href="/watch/{html.escape(n)}">{html.escape(n)}</a>（{size_mb:.1f} MB）</li>')
        body = "<h2>録画一覧</h2>" + ("<ul>" + "".join(items) + "</ul>" if items else "<p>録画がありません。</p>")
        self._send_html("録画一覧", body)

    def _watch(self, name: str):
        if self._resolve(name) is None:
            return self._not_found()
        safe = html.escape(unquote(name))
        self._send_html(safe, WATCH_BODY.format(name=safe))

    def _video(self, name: str):
        path = self._resolve(name)
        if path is None:
            return self._not_found()
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        start, end, status = 0, size - 1, HTTPStatus.OK
        if rng:
            parsed = parse_range(rng, size)
            if parsed is None:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            start, end = parsed
            status = HTTPStatus.PARTIAL_CONTENT
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # ブラウザがシークなどで接続を切った


def main():
    parser = argparse.ArgumentParser(description="録画データのビューア（デバッグ用）")
    parser.add_argument("--dir", default="movie", help="録画フォルダ（既定: movie）")
    add_common_args(parser)
    args = parser.parse_args()
    require_password(args)
    if not os.path.isdir(args.dir):
        sys.exit(f"エラー: 録画フォルダが見つかりません: {args.dir}")

    Handler.movie_dir = args.dir
    Handler.user = args.user
    Handler.password = args.password
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[viewer] {args.dir} を配信中: http://{args.host}:{args.port}/  （Ctrl+C で終了）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[viewer] 終了します。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
