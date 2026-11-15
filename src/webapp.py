"""監視カメラの Web アプリ（常駐）。ブラウザから、監視の開始・停止、ライブ映像、録画の再生ができる。

使い方（Pi 上で。SSH で起動して、そのまま放置する）:
    TOOLS_PASSWORD=xxxx python3 src/webapp.py --autostart
    → 同じ LAN のブラウザで http://<Pi の IP>:8000/ を開く（ユーザー名: admin）

仕組み:
- このアプリが surveillance.py を「子プロセス」として起動・停止する。
  停止は Ctrl+C と同じ信号（SIGINT）で、録画中なら MP4 を保存してから終わる。
- ライブ映像は、子プロセスが 127.0.0.1 だけで配信し、このアプリが中継する（LAN には直接出ない）。
- 録画の一覧・再生は tools/viewer.py の仕組みを使う（Range 対応・読み取り専用）。

注意:
- パスワード必須。通信は HTTP（暗号化されない）なので、LAN の中だけで使う。ポート開放はしない。
- このアプリが起動した監視だけを管理する。別に surveillance.py を動かしていると、カメラが使えず失敗する。
- 録画の自動削除はない。ディスクの空きを、画面で確認すること。
"""
import argparse
import base64
import http.client
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from _auth import add_common_args, require_password  # noqa: E402
import viewer  # noqa: E402  (tools/viewer.py: 録画の一覧・再生)
sys.path.insert(0, HERE)
import orientation  # noqa: E402  (src/orientation.py: カメラの向き)

DASHBOARD = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>監視カメラ</title>
<style>
body{font-family:sans-serif;max-width:960px;margin:1rem auto;padding:0 1rem}
img{width:100%;background:#000;image-rendering:pixelated;display:block}
.badge{display:inline-block;padding:.2rem .8rem;border-radius:4px;background:#ddd;font-weight:bold}
.badge.running{background:#2a9d4a;color:#fff}.badge.stopping{background:#e0a100;color:#fff}
button{font-size:1rem;padding:.5rem 1.2rem;margin-right:.5rem}
.rec{color:#c00;font-weight:bold}
pre{background:#111;color:#ddd;padding:.6rem;overflow:auto;max-height:18rem;font-size:.8rem}
.warn{background:#ffe9a8;padding:.4rem .8rem;border-radius:4px}
#bar{position:relative;height:28px;background:#e6e6e6;border-radius:4px;overflow:hidden}
#fill{height:100%;width:0;background:#2a9d4a;transition:width .15s}
#fill.over{background:#d33}
#thr{position:absolute;top:0;bottom:0;width:2px;background:#000}
#hist{width:100%;height:90px;background:#fafafa;border:1px solid #ddd;display:block;margin-top:.4rem}
#meterBox{margin:.8rem 0;display:none}
</style></head><body>
<h2>監視カメラ</h2>
<p>状態: <span id="state" class="badge">...</span> <span id="rec" class="rec"></span>
 <span id="uptime"></span></p>
<p><button id="btnStart">監視を開始</button><button id="btnStop">監視を停止</button>
 <a href="/recordings">録画一覧</a></p>
<p id="msg"></p>
<details id="setBox"><summary>カメラの向き</summary>
 <p>向き: <select id="rot"><option value="0">0°（そのまま）</option><option value="180">180°（上下逆さま）</option></select>
 <label><input type="checkbox" id="hf"> 左右反転</label>
 <label><input type="checkbox" id="vf"> 上下反転</label></p>
 <p><button id="btnSave">保存して再起動</button><button id="btnSaveOnly">保存のみ（次回の開始から）</button></p>
 <small>ライブ映像を見ながら直す。変更は、カメラを再起動すると反映される（録画中なら、保存してから再起動する）。</small>
</details>
<div id="liveBox"><img id="live" alt="live"><small>ライブ映像（320x240・白黒。検知用の映像）</small></div>
<div id="meterBox">
 <h3>動体検知メーター</h3>
 <p id="meterText">...</p>
 <div id="bar"><div id="fill"></div><div id="thr" title="しきい値"></div></div>
 <canvas id="hist" width="600" height="90"></canvas>
 <small>前のフレームとの差が <span id="pxThr">?</span> を超えた画素が、画面全体の何 % か（直近 1 秒の最大値）。
 黒い線（しきい値）を超えると「動き」と判定して録画する。下のグラフは、直近 60 秒の推移。</small>
</div>
<details id="thBox" open><summary>感度の調整（しきい値）</summary>
 <p>画素差: <input type="range" id="pxR" min="0" max="255" step="1"> <b id="pxV">-</b><br>
  <small>前のフレームとの明るさの差が、これを超えた画素を「変化した画素」と数える（小さいほど敏感）</small></p>
 <p>変化した画素の割合: <input type="range" id="crR" min="0.1" max="20" step="0.1"> <b id="crV">-</b><br>
  <small>変化した画素が、画面のこの割合を超えたら「動き」とみなす（小さいほど敏感）</small></p>
 <p><button id="btnThDefault">既定に戻す（30 / 3.0%）</button> <span id="thMsg"></span><br>
  <small>動かすと、すぐに反映して保存する（カメラの再起動は不要）。メーターの線で、効果を見ながら調整する。</small></p>
</details>
<p id="info"></p>
<p id="diskWarn" class="warn" style="display:none"></p>
<details id="logBox"><summary>ログ（最新）</summary><pre id="log"></pre></details>
<script>
const $=id=>document.getElementById(id);
let liveOn=false;
async function post(path){
  $('msg').textContent='...';
  try{
    const r=await fetch(path,{method:'POST',headers:{'X-Requested-With':'fetch'}});
    const j=await r.json(); $('msg').textContent=j.message||'';
  }catch(e){$('msg').textContent='通信に失敗しました'}
  refresh();
}
$('btnStart').onclick=()=>post('/api/start');
$('btnStop').onclick=()=>{ if(confirm('監視を停止しますか？（録画中なら、保存してから止まります）')) post('/api/stop'); };
async function saveSettings(restart){
  $('msg').textContent='...';
  const body={rotation:parseInt($('rot').value,10),hflip:$('hf').checked,vflip:$('vf').checked,restart:restart};
  try{
    const r=await fetch('/api/settings',{method:'POST',headers:{'X-Requested-With':'fetch','Content-Type':'application/json'},body:JSON.stringify(body)});
    const j=await r.json(); $('msg').textContent=j.message||'';
  }catch(e){$('msg').textContent='通信に失敗しました'}
  refresh();
}
// ---- しきい値の調整（スライダーを動かすと、少し待ってから、すぐに反映・保存する） ----
let thInit=false, thTimer=null;
function thLabels(){ $('pxV').textContent=$('pxR').value; $('crV').textContent=parseFloat($('crR').value).toFixed(1)+'%'; }
async function sendThresholds(){
  const body={pixel_threshold:parseInt($('pxR').value,10), change_ratio:Math.round(parseFloat($('crR').value)*10)/1000};
  try{
    const r=await fetch('/api/settings',{method:'POST',headers:{'X-Requested-With':'fetch','Content-Type':'application/json'},body:JSON.stringify(body)});
    const j=await r.json(); $('thMsg').textContent=j.message||'';
  }catch(e){$('thMsg').textContent='通信に失敗しました'}
}
function thChanged(){ thLabels(); clearTimeout(thTimer); thTimer=setTimeout(sendThresholds,400); }
$('pxR').oninput=thChanged; $('crR').oninput=thChanged;
$('btnThDefault').onclick=()=>{ $('pxR').value=30; $('crR').value=3; thChanged(); };
$('btnSave').onclick=()=>saveSettings(true);
$('btnSaveOnly').onclick=()=>saveSettings(false);
let setInit=false;   // 設定欄は、最初に 1 回だけ現在の値を入れる（編集中に上書きしない）
function fmt(s){s=Math.floor(s);const h=Math.floor(s/3600),m=Math.floor(s%3600/60);return (h?h+'時間':'')+m+'分'+(s%60)+'秒'}
async function refresh(){
  let j;
  try{ j=await (await fetch('/api/status')).json(); }catch(e){ $('state').textContent='接続できません'; return; }
  const names={running:'稼働中',stopping:'停止中...',stopped:'停止'};
  $('state').textContent=names[j.state]||j.state; $('state').className='badge '+j.state;
  $('rec').textContent=j.recording?'● 録画中':'';
  $('uptime').textContent=j.state==='running'?('（稼働 '+fmt(j.uptime_s)+'）'):'';
  $('btnStart').disabled=j.state!=='stopped'; $('btnStop').disabled=j.state!=='running';
  if(!setInit&&j.settings){$('rot').value=String(j.settings.rotation);$('hf').checked=j.settings.hflip;$('vf').checked=j.settings.vflip;setInit=true}
  $('btnSave').disabled=j.state==='stopping';
  if(!thInit&&j.settings){   // しきい値の欄も、最初に 1 回だけ現在の値を入れる（操作中に上書きしない）
    const crPct=Math.round(j.settings.change_ratio*1000)/10;
    $('crR').max=Math.max(20,crPct);
    $('pxR').value=j.settings.pixel_threshold; $('crR').value=crPct; thLabels(); thInit=true;
  }
  const on=j.state==='running';
  if(on&&!liveOn){$('live').src='/live.mjpg?'+Date.now();liveOn=true}
  if(!on&&liveOn){$('live').removeAttribute('src');liveOn=false}
  $('liveBox').style.display=on?'block':'none';
  let info='録画: '+j.recordings+' 件　ディスク空き: '+j.disk.free_gb+' GB / '+j.disk.total_gb+' GB';
  if(j.state==='stopped'&&j.last_exit_code!==null) info+='　（前回の終了コード: '+j.last_exit_code+'）';
  $('info').textContent=info;
  const w=$('diskWarn');
  if(j.disk.used_pct>=90){w.style.display='block';w.textContent='ディスクの使用率が '+j.disk.used_pct+'% です。録画データの整理が必要です。'}
  else w.style.display='none';
}
async function logRefresh(){
  if(!$('logBox').open) return;
  try{ $('log').textContent=await (await fetch('/api/log')).text(); }catch(e){}
}
// ---- 動体検知メーター ----
const HIST_SEC=60;
let hist=[], meterBusy=false;   // hist: {t: 時刻(ms), r: 割合}
const pct=x=>(x*100).toFixed(1)+'%';
function drawMeter(m){
  const thr=m.change_ratio||0.03, v=(m.ratio_peak!==undefined?m.ratio_peak:m.ratio), now=Date.now();
  hist.push({t:now,r:v});
  while(hist.length&&now-hist[0].t>HIST_SEC*1000) hist.shift();
  let peak=0, peak30=0;
  for(const h of hist){ if(h.r>peak) peak=h.r; if(now-h.t<=30000&&h.r>peak30) peak30=h.r; }
  const max=Math.max(thr*2, peak*1.15, 0.01);   // バーの右端。しきい値の 2 倍か、最近の最大値（大きい方）
  $('fill').style.width=Math.min(100,v/max*100)+'%';
  $('fill').className=v>thr?'over':'';
  $('thr').style.left=Math.min(100,thr/max*100)+'%';
  $('meterText').textContent='現在 '+pct(v)+' ／ しきい値 '+pct(thr)+' ／ 直近 30 秒の最大 '+pct(peak30)+(v>thr?'　→ 動きを検知':'');
  if(m.pixel_threshold!==null&&m.pixel_threshold!==undefined) $('pxThr').textContent=m.pixel_threshold;
  const cv=$('hist'), ctx=cv.getContext('2d'), W=cv.width, H=cv.height, y=r=>H-Math.min(1,r/max)*H;
  ctx.clearRect(0,0,W,H);
  ctx.lineWidth=1; ctx.strokeStyle='#000'; ctx.setLineDash([4,3]);
  ctx.beginPath(); ctx.moveTo(0,y(thr)); ctx.lineTo(W,y(thr)); ctx.stroke(); ctx.setLineDash([]);
  ctx.lineWidth=2; ctx.strokeStyle='#2a9d4a'; ctx.beginPath();
  hist.forEach((h,i)=>{const x=W-(now-h.t)/(HIST_SEC*1000)*W; if(i) ctx.lineTo(x,y(h.r)); else ctx.moveTo(x,y(h.r));});
  ctx.stroke();
}
async function meterPoll(){
  if(meterBusy) return;   // 前の取得が終わっていなければ、重ねない
  meterBusy=true;
  try{
    const m=await (await fetch('/api/meter')).json();
    if(m.running){ $('meterBox').style.display='block'; drawMeter(m); }
    else { $('meterBox').style.display='none'; hist=[]; }
  }catch(e){} finally{ meterBusy=false; }
}
setInterval(meterPoll,500);
refresh(); setInterval(refresh,2000); setInterval(logRefresh,3000);
$('logBox').addEventListener('toggle',logRefresh);
</script></body></html>"""


class Settings:
    """カメラの向きと、動体検知のしきい値の設定。workdir/settings.json に保存し、Web アプリを再起動しても残す。"""

    KEYS = ("rotation", "hflip", "vflip", "pixel_threshold", "change_ratio")
    ORIENTATION_KEYS = ("rotation", "hflip", "vflip")

    def __init__(self, path, defaults):
        self.path = path
        self.lock = threading.Lock()
        self.values = self.validate(defaults)
        try:
            with open(path, encoding="utf-8") as f:
                # 古い版の設定ファイル（キーが足りない）でも読めるよう、起動時の指定を土台にして重ねる
                self.values = self.validate({**self.values, **json.load(f)})
        except (OSError, ValueError, TypeError):
            pass   # ファイルがない・壊れている場合は、既定値のまま

    @staticmethod
    def validate(d):
        """正しい設定だけを通す。不正なら ValueError。"""
        if not isinstance(d, dict):
            raise ValueError("設定の形式が正しくありません。")
        rotation, hflip, vflip = d.get("rotation", 0), d.get("hflip", False), d.get("vflip", False)
        if isinstance(rotation, bool) or rotation not in orientation.ROTATIONS:
            raise ValueError("rotation は 0 か 180 です。")
        if not isinstance(hflip, bool) or not isinstance(vflip, bool):
            raise ValueError("hflip と vflip は true / false です。")
        pixel, ratio = d.get("pixel_threshold", 30), d.get("change_ratio", 0.03)
        if isinstance(pixel, bool) or not isinstance(pixel, int) or not 0 <= pixel <= 255:
            raise ValueError("pixel_threshold は 0〜255 の整数です。")
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 < ratio <= 1:
            raise ValueError("change_ratio は 0 より大きく 1 以下の数です。")
        return {"rotation": int(rotation), "hflip": hflip, "vflip": vflip,
                "pixel_threshold": pixel, "change_ratio": float(ratio)}

    def get(self):
        with self.lock:
            return dict(self.values)

    def set(self, d):
        values = self.validate(d)
        with self.lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(values, f)
            os.replace(tmp, self.path)   # 書き込み途中で止まっても、壊れたファイルを残さない
            self.values = values


class Manager:
    """surveillance.py の子プロセスを、起動・停止・監視する。"""

    STOP_WAIT_SIGINT = 30   # 秒。録画中の保存（MP4 への変換）を待つ
    STOP_WAIT_SIGTERM = 10  # 秒

    def __init__(self, cmd, workdir, env, log_path):
        self.cmd, self.workdir, self.env, self.log_path = cmd, workdir, env, log_path
        self.lock = threading.Lock()
        self.proc = None
        self.state = "stopped"   # stopped / running / stopping
        self.started_at = None
        self.last_exit_code = None
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def start(self):
        with self.lock:
            if self.state != "stopped":
                return False, "すでに起動中です。"
            cmd = self.cmd() if callable(self.cmd) else self.cmd   # 起動のたびに、最新の設定でコマンドを作る
            log = open(self.log_path, "ab")
            log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} 監視を開始 =====\n".encode())
            log.flush()
            try:
                # start_new_session: 端末の Ctrl+C が、子に直接届かないようにする（停止はこのアプリが行う）
                self.proc = subprocess.Popen(cmd, cwd=self.workdir, env=self.env, stdout=log,
                                             stderr=subprocess.STDOUT, start_new_session=True)
            except OSError as e:
                log.close()
                return False, f"起動に失敗しました: {e}"
            log.close()
            self.state, self.started_at = "running", time.monotonic()
            threading.Thread(target=self._watch, args=(self.proc,), daemon=True).start()
            return True, "監視を開始しました。"

    def _watch(self, proc):
        code = proc.wait()
        with self.lock:
            if self.proc is proc:
                self.state, self.last_exit_code, self.started_at = "stopped", code, None

    def stop(self):
        with self.lock:
            if self.state != "running":
                return False, "監視は動いていません。"
            self.state = "stopping"
            proc = self.proc
        threading.Thread(target=self._terminate, args=(proc,), daemon=True).start()
        return True, "停止しています（録画中なら、保存してから止まります）。"

    def _terminate(self, proc):
        try:
            proc.send_signal(signal.SIGINT)   # Ctrl+C と同じ: 録画の保存・カメラの解放をして終わる
            proc.wait(timeout=self.STOP_WAIT_SIGINT)
        except subprocess.TimeoutExpired:
            try:
                proc.terminate()
                proc.wait(timeout=self.STOP_WAIT_SIGTERM)
            except subprocess.TimeoutExpired:
                proc.kill()
        except ProcessLookupError:
            pass

    def restart(self):
        """動いていれば、止めてから起動し直す。止まっていれば、起動する。"""
        with self.lock:
            state = self.state
        if state == "stopped":
            return self.start()
        if state == "stopping":
            return False, "停止処理中です。止まってから、もう一度操作してください。"
        self.stop()
        threading.Thread(target=self._start_after_stop, daemon=True).start()
        return True, "再起動しています（録画中なら、保存してから再起動します）。"

    def _start_after_stop(self):
        deadline = time.monotonic() + self.STOP_WAIT_SIGINT + self.STOP_WAIT_SIGTERM + 5
        while time.monotonic() < deadline:
            with self.lock:
                if self.state == "stopped":
                    break
            time.sleep(0.2)
        self.start()

    def stop_and_wait(self):
        """このアプリの終了時に、子プロセスも止める。"""
        with self.lock:
            proc, running = self.proc, self.state in ("running", "stopping")
        if proc and running and proc.poll() is None:
            self._terminate(proc)

    def snapshot(self):
        with self.lock:
            return {"state": self.state, "pid": self.proc.pid if self.proc and self.state != "stopped" else None,
                    "uptime_s": round(time.monotonic() - self.started_at, 1) if self.started_at else 0,
                    "last_exit_code": self.last_exit_code}


def tail_lines(path, n=40, max_bytes=32768):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            data = f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(data.splitlines()[-n:])


class Handler(viewer.Handler):
    """viewer.Handler（録画の一覧・再生）に、ダッシュボードと操作の API を足したもの。"""
    server_version = "CameraApp"
    manager: Manager = None
    settings: Settings = None
    live_port = 0
    workdir = "."

    def log_message(self, fmt, *args):
        sys.stderr.write("[webapp] %s - %s\n" % (self.address_string(), fmt % args))

    def _send_html(self, title, body, status=HTTPStatus.OK):
        # 録画一覧・再生のページに、ホームへ戻るリンクを足す
        super()._send_html(title, '<p><a href="/">&larr; ホーム</a></p>' + body, status)

    def _send_json(self, obj, status=HTTPStatus.OK):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ---- GET ----
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            if not self._authorized():
                return
            data = DASHBOARD.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/status":
            if self._authorized():
                self._send_json(self._status())
        elif path == "/api/meter":
            if self._authorized():
                self._send_json(self._meter())
        elif path == "/api/log":
            if self._authorized():
                data = tail_lines(os.path.join(self.workdir, "logs", "surveillance.log")).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
        elif path == "/live.mjpg":
            if self._authorized():
                self._live()
        else:
            super().do_GET()   # /recordings, /watch/..., /video/...（認証は super 側で行う）

    def _status(self):
        s = self.manager.snapshot()
        recording = False
        if s["state"] == "running":
            recording = self._live_recording()
        try:
            names = [n for n in os.listdir(self.movie_dir) if viewer.NAME_RE.match(n)]
        except OSError:
            names = []
        du = shutil.disk_usage(self.workdir)
        s.update(recording=recording, recordings=len(names), settings=self.settings.get(),
                 disk={"free_gb": round(du.free / 1e9, 1), "total_gb": round(du.total / 1e9, 1),
                       "used_pct": round(du.used / du.total * 100, 1)})
        return s

    def _upstream_headers(self):
        token = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
        return {"Authorization": "Basic " + token}

    def _live_status(self) -> dict:
        """子プロセスのライブ配信の /status（録画中か、変化した画素の割合、しきい値）を得る。取れなければ空の辞書。"""
        try:
            conn = http.client.HTTPConnection("127.0.0.1", self.live_port, timeout=2)
            conn.request("GET", "/status", headers=self._upstream_headers())
            resp = conn.getresponse()
            data = json.loads(resp.read()) if resp.status == 200 else {}
            conn.close()
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, http.client.HTTPException):
            return {}

    def _live_recording(self) -> bool:
        return bool(self._live_status().get("recording"))

    def _meter(self) -> dict:
        """動体検知メーター用: 変化した画素の割合と、しきい値。監視が動いていなければ running=false。"""
        if self.manager.snapshot()["state"] != "running":
            return {"running": False}
        s = self._live_status()
        th = s.get("thresholds") or {}
        if "ratio" not in s:
            return {"running": False}
        return {"running": True, "recording": bool(s.get("recording")), "ratio": s["ratio"],
                "ratio_peak": s.get("ratio_peak", s["ratio"]),   # 直近 1 秒の最大（短い spike を見逃さない）
                "change_ratio": th.get("change_ratio"), "pixel_threshold": th.get("pixel_threshold")}

    def _live(self):
        """子プロセスのライブ映像（MJPEG）を、そのまま中継する。"""
        if self.manager.snapshot()["state"] != "running":
            return self._send_json({"ok": False, "message": "監視が動いていません。"}, HTTPStatus.SERVICE_UNAVAILABLE)
        conn = http.client.HTTPConnection("127.0.0.1", self.live_port, timeout=30)
        try:
            conn.request("GET", "/stream.mjpg", headers=self._upstream_headers())
            resp = conn.getresponse()
            if resp.status != 200:
                conn.close()
                return self._send_json({"ok": False, "message": "ライブ映像を取得できません。"}, HTTPStatus.BAD_GATEWAY)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", resp.getheader("Content-Type", "multipart/x-mixed-replace; boundary=FRAME"))
            self.send_header("Cache-Control", "no-cache, private")
            self.end_headers()
            while True:
                chunk = resp.read1(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError, OSError, http.client.HTTPException):
            pass   # ブラウザが閉じた、または子プロセスが止まった
        finally:
            conn.close()

    # ---- POST（開始・停止） ----
    def _csrf_ok(self) -> bool:
        """他のサイトからの操作を防ぐ。自前の画面の fetch だけが付けるヘッダーと、Origin を確認する。"""
        if self.headers.get("X-Requested-With") != "fetch":
            return False
        origin = self.headers.get("Origin")
        return not origin or urlparse(origin).netloc == self.headers.get("Host")

    def _push_params(self, pixel, ratio) -> bool:
        """動いている監視（子プロセス）に、新しいしきい値を送る。カメラの再起動は要らない。"""
        try:
            conn = http.client.HTTPConnection("127.0.0.1", self.live_port, timeout=3)
            conn.request("POST", "/params", body=json.dumps({"pixel_threshold": pixel, "change_ratio": ratio}),
                         headers=dict(self._upstream_headers(), **{"Content-Type": "application/json"}))
            ok = conn.getresponse().status == 200
            conn.close()
            return ok
        except (OSError, http.client.HTTPException):
            return False

    def _save_settings(self):
        """設定（向き・しきい値）を保存する。(ok, メッセージ, HTTP ステータス) を返す。
        送られた項目だけを、今の設定に重ねる。しきい値は、動いている監視にすぐ反映する（再起動は不要）。
        向きは、restart が true なら、反映のため再起動する。"""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > 2048:
            return False, "リクエストの大きさが正しくありません。", HTTPStatus.BAD_REQUEST
        try:
            body = json.loads(self.rfile.read(n))
            if not isinstance(body, dict):
                raise ValueError("形式が正しくありません。")
            provided = {k: v for k, v in body.items() if k in Settings.KEYS}
            if not provided:
                raise ValueError("変更する項目がありません。")
            old = self.settings.get()
            new = Settings.validate({**old, **provided})
        except ValueError as e:
            return False, f"設定が正しくありません: {e}", HTTPStatus.BAD_REQUEST
        self.settings.set(new)

        running = self.manager.snapshot()["state"] == "running"
        msgs, ok, status = ["保存しました。"], True, HTTPStatus.OK
        if "pixel_threshold" in provided or "change_ratio" in provided:
            if running and self._push_params(new["pixel_threshold"], new["change_ratio"]):
                msgs.append("しきい値を反映しました。")
            elif running:
                msgs.append("しきい値を反映できませんでした（次にカメラを起動したときから反映されます）。")
            else:
                msgs.append("しきい値は、次に監視を開始したときから反映されます。")
        if any(k in provided for k in Settings.ORIENTATION_KEYS):
            if body.get("restart") is True:
                ok, msg = self.manager.restart()
                msgs.append(msg)
                status = HTTPStatus.OK if ok else HTTPStatus.CONFLICT
            elif running:
                msgs.append("向きは、次にカメラを起動したときから反映されます。")
        return ok, "".join(msgs), status

    def do_POST(self):
        if not self._authorized():
            return
        if not self._csrf_ok():
            return self._send_json({"ok": False, "message": "不正なリクエストです。"}, HTTPStatus.FORBIDDEN)
        path = self.path.split("?", 1)[0]
        if path == "/api/start":
            ok, msg = self.manager.start()
        elif path == "/api/stop":
            ok, msg = self.manager.stop()
        elif path == "/api/settings":
            ok, msg, status = self._save_settings()
            return self._send_json({"ok": ok, "message": msg}, status)
        else:
            return self._send_json({"ok": False, "message": "見つかりません。"}, HTTPStatus.NOT_FOUND)
        self._send_json({"ok": ok, "message": msg}, HTTPStatus.OK if ok else HTTPStatus.CONFLICT)


def build_command(args, settings=None):
    """子プロセス（監視）の起動コマンド。向きとしきい値は、保存された設定（なければ起動時の指定）を使う。"""
    s = settings or {"rotation": args.rotation, "hflip": args.hflip, "vflip": args.vflip,
                     "pixel_threshold": args.pixel_threshold, "change_ratio": args.change_ratio}
    options = (["--rotation", str(s["rotation"])] + (["--hflip"] if s["hflip"] else []) + (["--vflip"] if s["vflip"] else [])
               + ["--pixel-threshold", str(s["pixel_threshold"]), "--change-ratio", str(s["change_ratio"])])
    if args.child_cmd:   # テスト用: 監視の代わりに別のコマンドを動かす
        return shlex.split(args.child_cmd) + options
    return [sys.executable, "-u", os.path.join(HERE, "surveillance.py"),
            "--live-port", str(args.live_port), "--live-host", "127.0.0.1", "--live-user", args.user] + options


def main():
    parser = argparse.ArgumentParser(description="監視カメラの Web アプリ（開始・停止・ライブ映像・録画の再生）")
    add_common_args(parser)
    orientation.add_arguments(parser)   # 向きの初期値（画面で保存した設定があれば、そちらを優先する）
    parser.add_argument("--workdir", default=".",
                        help="録画（movie/）とログ（logs/）の場所。既定: 今いるフォルダ")
    parser.add_argument("--autostart", action="store_true", help="このアプリの起動と同時に、監視を開始する")
    parser.add_argument("--live-port", type=int, default=8002,
                        help="監視がライブ映像を出す内部ポート（127.0.0.1 のみ）。既定: 8002")
    parser.add_argument("--pixel-threshold", type=int, default=30, help="監視の画素差のしきい値（既定: 30）")
    parser.add_argument("--change-ratio", type=float, default=0.03, help="監視の変化割合のしきい値（既定: 0.03）")
    parser.add_argument("--child-cmd", default=None, help="（テスト用）監視の代わりに動かすコマンド")
    args = parser.parse_args()
    require_password(args)

    workdir = os.path.abspath(args.workdir)
    movie_dir = os.path.join(workdir, "movie")
    os.makedirs(movie_dir, exist_ok=True)

    env = dict(os.environ, TOOLS_PASSWORD=args.password, PYTHONUNBUFFERED="1")   # パスワードは引数ではなく環境変数で渡す
    try:
        settings = Settings(os.path.join(workdir, "settings.json"),
                            {"rotation": args.rotation, "hflip": args.hflip, "vflip": args.vflip,
                             "pixel_threshold": args.pixel_threshold, "change_ratio": args.change_ratio})
    except ValueError as e:
        sys.exit(f"エラー: 起動時の指定が正しくありません: {e}")
    manager = Manager(lambda: build_command(args, settings.get()), workdir, env,
                      os.path.join(workdir, "logs", "surveillance.log"))

    Handler.manager, Handler.settings, Handler.live_port, Handler.workdir = manager, settings, args.live_port, workdir
    Handler.movie_dir, Handler.user, Handler.password = movie_dir, args.user, args.password
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True

    def shutdown(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, shutdown)
    # バックグラウンド（& や nohup）で起動されると SIGINT が無視されていることがあるので、受け付けるようにする
    signal.signal(signal.SIGINT, signal.default_int_handler)

    print(f"[webapp] http://{args.host}:{args.port}/ （ユーザー名: {args.user}）  録画: {movie_dir}", flush=True)
    if args.autostart:
        ok, msg = manager.start()
        print(f"[webapp] {msg}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[webapp] 終了します。監視を止めています...", flush=True)
    finally:
        manager.stop_and_wait()
        server.server_close()


if __name__ == "__main__":
    main()
