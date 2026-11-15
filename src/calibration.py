"""動体検知のしきい値の「自動調整」。

静止状態を数十秒測り、「静止していても、フレーム間の差が出る量（ノイズ・明るさの揺れ）」から、
ノイズに反応しない、しきい値の目安を出す。

考え方:
- 画素差のしきい値 t を決めると、「前のフレームとの差が t を超えた画素」が、画面の何 % かが決まる（割合 R(t)）。
- 静止状態では、t が小さいほど R(t) が大きい（ノイズも「変化」に数えるため）。t を上げると R(t) は急に小さくなる。
- そこで、静止中の R(t) の最大値が、十分小さくなる最小の t を、画素差のしきい値にする。
- 割合のしきい値は、そのときの静止中の最大値の数倍（余裕）にする。

注意: ここの定数（0.2% や 3 倍など）は、経験則による目安であり、実機のカメラで検証した値ではない。
      推奨値は、そのまま信じず、メーターで、静止時と動いたときの両方を確認すること。
"""
import ctypes
import time

import numpy as np

MIN_PIXEL = 5            # 推奨する画素差の下限（これ未満は、ノイズに反応しやすすぎるため推奨しない）
MAX_PIXEL = 40           # 画素差をここまで上げても静止時の変化が収まらなければ、「静止状態ではない」と判断する（これ以上は鈍すぎる）
NOISE_OK = 0.002         # 静止中の最大の割合が、これ以下なら「ノイズが収まった」とみなす（0.2%）
RATIO_FACTOR = 3.0       # 割合のしきい値 = 静止中の最大値 × この倍率
RATIO_MIN = 0.005        # 割合のしきい値の下限（0.5%）
RATIO_MAX = 0.2          # これを超えるなら、静止状態ではない（20%）
MIN_FRAMES = 10          # これ未満のフレームでは、結論を出さない
TABLE_PIXELS = (5, 10, 15, 20, 30, 40, 60)   # 画面に表示する、画素差ごとの静止時の最大値


class Calibrator:
    """フレームごとの差の分布（256 個）を集めて、静止時の最大の割合を求める。"""

    def __init__(self):
        self.max_ratio = np.zeros(256)   # max_ratio[t]: 静止中に、「差が t を超えた画素」が占めた割合の最大値
        self.frames = 0

    def add(self, hist, size: int) -> None:
        """hist[d] = 差が d の画素の数（256 個）、size = 画素の総数。"""
        hist = np.asarray(hist, dtype=np.float64)
        tail = np.cumsum(hist[::-1])[::-1]        # tail[d] = 差が d 以上の画素数
        ratio = np.append(tail[1:], 0.0) / size   # ratio[t] = 差が t を超えた画素数 / 総数
        np.maximum(self.max_ratio, ratio, out=self.max_ratio)
        self.frames += 1

    def result(self) -> dict:
        """推奨値と、表示用の表を返す。結論が出せないときは ok=False とメッセージ。"""
        table = [{"pixel": t, "max_ratio": round(float(self.max_ratio[t]), 5)} for t in TABLE_PIXELS]
        base = {"frames": self.frames, "table": table}
        if self.frames < MIN_FRAMES:
            return {**base, "ok": False, "message": f"フレームが足りません（{self.frames} 枚）。もう一度測ってください。"}
        candidates = np.nonzero(self.max_ratio[MIN_PIXEL:MAX_PIXEL + 1] <= NOISE_OK)[0]
        if len(candidates) == 0:
            worst = float(self.max_ratio[MAX_PIXEL])
            return {**base, "ok": False,
                    "message": f"画素差 {MAX_PIXEL} でも、静止中に画面の {worst * 100:.1f}% が変化しました。"
                               "測定中に何かが動いた、照明のちらつき、自動露出の変化などが考えられます。"
                               "動かない状態で、もう一度測ってください。"}
        pixel = int(candidates[0]) + MIN_PIXEL
        quiet = float(self.max_ratio[pixel])
        ratio = min(1.0, max(RATIO_MIN, np.ceil(quiet * RATIO_FACTOR * 1000) / 1000))   # 0.1% 単位で切り上げ
        if ratio > RATIO_MAX:
            return {**base, "ok": False,
                    "message": f"静止中の変化が大きく（{quiet * 100:.1f}%）、安定した値を出せません。"
                               "動かない状態で、もう一度測ってください。"}
        return {**base, "ok": True, "pixel_threshold": pixel, "change_ratio": round(float(ratio), 4),
                "static_max_ratio": round(quiet, 5)}


class CalibrationRunner:
    """監視ループの中で、自動調整の開始・測定・結果の公開を行う。

    lib: libmotion.so（set_hist_enabled / get_diff_hist が必要）
    live: LiveView（calibration に状態を書く）
    """

    def __init__(self, lib, live):
        self.lib, self.live = lib, live
        self.calibrator = None
        self.until = 0.0
        self.started = 0.0
        self.seconds = 0
        self._last_publish = 0.0
        self._buf = (ctypes.c_uint * 256)()

    @property
    def running(self) -> bool:
        return self.calibrator is not None

    def handle_command(self, cmd) -> None:
        """cmd = ("start", 秒数) / ("cancel", None) / None。"""
        if cmd is None:
            return
        action, seconds = cmd
        if action == "start" and not self.running:
            self.calibrator, self.seconds = Calibrator(), int(seconds)
            self.started = time.monotonic()
            self.until = self.started + self.seconds
            self.lib.set_hist_enabled(1)
            self._publish(force=True)
            print(f"[CALIBRATE] 自動調整を開始（{self.seconds} 秒）。静止状態を測ります。", flush=True)
        elif action == "cancel" and self.running:
            self._finish(cancelled=True)

    def after_detect(self) -> None:
        """detect_motion の直後に、毎フレーム呼ぶ。"""
        if not self.running:
            return
        size = self.lib.get_diff_hist(self._buf)
        if size:
            self.calibrator.add(np.frombuffer(self._buf, dtype=np.uint32), size)
        if time.monotonic() >= self.until:
            self._finish()
        else:
            self._publish()

    def _publish(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_publish < 0.5:
            return
        self._last_publish = now
        self.live.calibration = {"state": "running", "seconds": self.seconds,
                                 "elapsed": round(now - self.started, 1), "frames": self.calibrator.frames}

    def _finish(self, cancelled: bool = False) -> None:
        self.lib.set_hist_enabled(0)
        calibrator, self.calibrator = self.calibrator, None
        if cancelled:
            self.live.calibration = {"state": "idle"}
            print("[CALIBRATE] 中止しました。", flush=True)
            return
        result = calibrator.result()
        self.live.calibration = {"state": "done" if result["ok"] else "failed", "result": result}
        if result["ok"]:
            print(f"[CALIBRATE] 完了: 推奨 画素差={result['pixel_threshold']} 割合={result['change_ratio']}"
                  f"（静止時の最大 {result['static_max_ratio'] * 100:.2f}%、{result['frames']} フレーム）", flush=True)
        else:
            print(f"[CALIBRATE] 失敗: {result['message']}", flush=True)
