"""検知ループの計測ツール（実機の Pi Zero 2 W で実行する）。

モード:
  detect   本システムの構成。検知用 320x240 の Y プレーンだけを CPU で処理する（録画用 1080p は別系統）。
  fullhd   比較用。フル HD（1920x1080）の Y プレーンをそのまま CPU で処理する。
           2 系統に分けた効果を、数字で比べるためのもの。
  latency  動きを検知してから、録画が始まるまでの時間を測る（手順は docs/benchmark.md）。

使い方（例）:
    python3 tools/benchmark.py detect --duration 60
    python3 tools/benchmark.py fullhd --duration 60
    python3 tools/benchmark.py detect --duration 60 --record      # 録画（H.264）しながら
    python3 tools/benchmark.py latency --trials 5

条件をそろえて比べるコツ: 画面を動かさず（静止状態で）、同じ時間・同じ設定で、各モードを実行する。
結果は CSV（results/）に保存される。数値は、実機で測った値だけを README に書く。

注意: 監視（surveillance.py）と同時には実行できない（カメラは 1 つのプログラムしか使えない）。
"""
import argparse
import os
import sys
import time
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _metrics import CsvLog, Sampler, read_throttled  # noqa: E402

LIB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "libmotion.so")

COLUMNS = ["timestamp", "mode", "elapsed_s", "fps", "avg_capture_ms", "avg_detect_ms", "motion_count",
           "cpu_process_pct", "cpu_system_pct", "rss_kb", "mem_available_kb",
           "pixel_threshold", "change_ratio", "record"]
LATENCY_COLUMNS = ["timestamp", "trial", "detect_to_record_call_ms", "detect_to_first_frame_ms",
                   "pixel_threshold", "change_ratio"]


def load_lib(args):
    import ctypes
    from numpy.ctypeslib import ndpointer
    if not os.path.exists(LIB_PATH):
        sys.exit(f"エラー: {LIB_PATH} がありません。先に `make -C src` を実行してください。")
    lib = ctypes.CDLL(LIB_PATH)
    lib.detect_motion.argtypes = [ndpointer(ctypes.c_uint8, flags="C_CONTIGUOUS"), ctypes.c_int, ctypes.c_int]
    lib.detect_motion.restype = ctypes.c_int
    lib.set_motion_params.argtypes = [ctypes.c_int, ctypes.c_double]
    lib.set_motion_params.restype = ctypes.c_int
    lib.reset_motion.restype = None
    if lib.set_motion_params(args.pixel_threshold, args.change_ratio) != 0:
        sys.exit("エラー: しきい値が範囲外です。")
    return lib


def open_camera():
    from picamera2 import Picamera2
    try:
        return Picamera2()
    except Exception as e:
        sys.exit("エラー: カメラを開けません。src/surveillance.py や tools/preview.py が動いていないか確認してください。\n"
                 f"詳細: {e}")


def summarize(rows, mode):
    """CSV に書いた行から、平均・最大などを出力する。"""
    if not rows:
        print("（記録がありません）")
        return

    def col(name):
        return [r[name] for r in rows if r.get(name) not in (None, "")]
    fps, cpu_p, cpu_s, rss = col("fps"), col("cpu_process_pct"), col("cpu_system_pct"), col("rss_kb")
    print("\n===== まとめ =====")
    print(f"モード            : {mode}")
    print(f"記録した区間の数  : {len(rows)}")
    print(f"fps               : 平均 {sum(fps)/len(fps):.1f}  最小 {min(fps):.1f}  最大 {max(fps):.1f}")
    print(f"CPU(プロセス, %)  : 平均 {sum(cpu_p)/len(cpu_p):.1f}  最大 {max(cpu_p):.1f}   （100% = 1 コア使い切り）")
    print(f"CPU(機械全体, %)  : 平均 {sum(cpu_s)/len(cpu_s):.1f}  最大 {max(cpu_s):.1f}")
    print(f"RSS (kB)          : 最初 {rss[0]}  最後 {rss[-1]}  最小 {min(rss)}  最大 {max(rss)}")
    print(f"throttled         : {read_throttled() or '（取得できず）'}   （0x0 なら電圧不足などなし）")
    print("==================\n")


def run_detect(args, mode):
    from picamera2 import Picamera2  # noqa: F401  (存在確認)
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FileOutput

    lib = load_lib(args)
    picam2 = open_camera()
    if mode == "detect":
        config = picam2.create_video_configuration(
            main={"size": (1920, 1080), "format": "YUV420"}, lores={"size": (320, 240), "format": "YUV420"})
        stream, w, h = "lores", 320, 240
    else:  # fullhd
        config = picam2.create_video_configuration(main={"size": (1920, 1080), "format": "YUV420"})
        stream, w, h = "main", 1920, 1080
    picam2.configure(config)
    if args.record:
        picam2.start_recording(H264Encoder(bitrate=2000000), FileOutput("/dev/null"))
    else:
        picam2.start()

    out = args.out or f"results/{mode}{'_rec' if args.record else ''}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    log = CsvLog(out, COLUMNS)
    rows = []
    try:
        print(f"[bench] {mode}: カメラを安定させています（2 秒）...", flush=True)
        time.sleep(2)
        lib.reset_motion()
        sampler = Sampler(os.getpid(), with_throttled=False)
        print(f"[bench] 計測開始: {args.duration:g} 秒、{args.interval:g} 秒ごとに記録 → {out}", flush=True)
        print("[bench] 静止状態で測る場合は、カメラの前で動かないでください。", flush=True)

        pc = time.perf_counter

        def record_interval(now):
            """直前の区間の集計を CSV に書き、カウンタを戻す。"""
            nonlocal last, frames, motions, cap_s, det_s
            dt = now - last
            row = sampler.sample()
            row.update(timestamp=datetime.now().isoformat(timespec="seconds"), mode=mode,
                       elapsed_s=round(now - start, 1), fps=round(frames / dt, 2),
                       avg_capture_ms=round(cap_s / frames * 1000, 2), avg_detect_ms=round(det_s / frames * 1000, 3),
                       motion_count=motions, pixel_threshold=args.pixel_threshold,
                       change_ratio=args.change_ratio, record=int(args.record))
            log.write(row)
            rows.append(row)
            print(f"[bench] {row['elapsed_s']:>6.0f}s fps={row['fps']:<6} cpu(proc)={row['cpu_process_pct']}% "
                  f"rss={row['rss_kb']}kB detect={row['avg_detect_ms']}ms", flush=True)
            last, frames, motions, cap_s, det_s = now, 0, 0, 0.0, 0.0

        start = last = last_frame_t = pc()
        frames = motions = 0
        cap_s = det_s = 0.0
        while pc() - start < args.duration:
            t0 = pc()
            arr = picam2.capture_array(stream)
            t1 = pc()
            gray = np.ascontiguousarray(arr[:h, :w])
            r = lib.detect_motion(gray, w, h)
            t2 = pc()
            frames += 1
            cap_s += t1 - t0
            det_s += t2 - t1
            motions += 1 if r == 1 else 0
            last_frame_t = t2
            if t2 - last >= args.interval:
                record_interval(t2)
            if args.sleep > 0:
                time.sleep(args.sleep)
        # 最後の中途半端な区間も、短すぎなければ記録する（短い区間は fps が不安定になるため捨てる）。
        # 区間の終わりは「最後のフレームの時刻」にする（最後の待ちまで含めると、fps が低く出る）。
        if frames > 0 and last_frame_t - last >= min(args.interval, 1.0) * 0.5:
            record_interval(last_frame_t)
    except KeyboardInterrupt:
        print("\n[bench] 中断しました。ここまでの記録は保存されています。")
    finally:
        log.close()
        try:
            if args.record:
                picam2.stop_recording()
            else:
                picam2.stop()
        finally:
            picam2.close()
    print(f"[bench] 保存しました: {out}")
    summarize(rows, mode + (" + record" if args.record else ""))


def run_latency(args):
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FileOutput

    class TimedOutput(FileOutput):
        """最初のフレームがエンコーダから出てきた時刻を記録する。"""
        first_frame_time = None

        def outputframe(self, *a, **kw):
            if self.first_frame_time is None:
                self.first_frame_time = time.perf_counter()
            return super().outputframe(*a, **kw)

    lib = load_lib(args)
    picam2 = open_camera()
    config = picam2.create_video_configuration(
        main={"size": (1920, 1080), "format": "YUV420"}, lores={"size": (320, 240), "format": "YUV420"})
    picam2.configure(config)
    picam2.start()
    out = args.out or f"results/latency_{datetime.now():%Y%m%d_%H%M%S}.csv"
    log = CsvLog(out, LATENCY_COLUMNS)
    pc = time.perf_counter
    results = []
    try:
        time.sleep(2)
        for i in range(1, args.trials + 1):
            lib.reset_motion()
            print(f"[latency] 試行 {i}/{args.trials}: カメラの前で動いてください（60 秒で打ち切り）...", flush=True)
            deadline = pc() + 60
            detected = False
            while pc() < deadline:
                gray = np.ascontiguousarray(picam2.capture_array("lores")[:240, :320])
                if lib.detect_motion(gray, 320, 240) == 1:
                    detected = True
                    break
                time.sleep(0.05)
            if not detected:
                print("[latency] 動きが検知されませんでした。中止します。")
                break
            t_detect = pc()
            output = TimedOutput("/dev/null")
            picam2.start_recording(H264Encoder(bitrate=2000000), output)
            t_called = pc()
            wait_until = pc() + 5
            while output.first_frame_time is None and pc() < wait_until:
                time.sleep(0.002)
            first = output.first_frame_time
            row = {"timestamp": datetime.now().isoformat(timespec="seconds"), "trial": i,
                   "detect_to_record_call_ms": round((t_called - t_detect) * 1000, 1),
                   "detect_to_first_frame_ms": round((first - t_detect) * 1000, 1) if first else "",
                   "pixel_threshold": args.pixel_threshold, "change_ratio": args.change_ratio}
            log.write(row)
            results.append(row)
            print(f"[latency] 検知 → start_recording 完了: {row['detect_to_record_call_ms']} ms / "
                  f"検知 → 最初のフレーム: {row['detect_to_first_frame_ms'] or 'タイムアウト'} ms", flush=True)
            time.sleep(2)
            picam2.stop_recording()
            # surveillance.py と同じ、カメラの再起動（回避策）
            picam2.stop()
            time.sleep(0.5)
            picam2.start()
            print("[latency] 動かずに待ってください（3 秒）...", flush=True)
            time.sleep(3)
    except KeyboardInterrupt:
        print("\n[latency] 中断しました。")
    finally:
        log.close()
        try:
            picam2.stop()
        finally:
            picam2.close()
    print(f"[latency] 保存しました: {out}")
    vals = [r["detect_to_first_frame_ms"] for r in results if r["detect_to_first_frame_ms"] != ""]
    if vals:
        print(f"検知 → 最初のフレーム: 平均 {sum(vals)/len(vals):.1f} ms  最小 {min(vals)}  最大 {max(vals)}  （n={len(vals)}）")
    print("注意: これは「検知した瞬間」からの時間。実際に動いてから検知されるまでの時間は含まれない。")


def main():
    p = argparse.ArgumentParser(description="検知ループの計測ツール")
    p.add_argument("mode", choices=["detect", "fullhd", "latency"])
    p.add_argument("--duration", type=float, default=60, help="計測する長さ（秒）。既定: 60")
    p.add_argument("--interval", type=float, default=1, help="記録の間隔（秒）。既定: 1（長時間なら 60 など）")
    p.add_argument("--sleep", type=float, default=0.05,
                   help="ループごとの待ち（秒）。既定: 0.05（surveillance.py と同じ）。0 にすると処理速度の上限を測れる")
    p.add_argument("--record", action="store_true", help="録画（H.264 エンコード）をしながら測る（/dev/null に出力）")
    p.add_argument("--trials", type=int, default=5, help="latency モードの試行回数。既定: 5")
    p.add_argument("--pixel-threshold", type=int, default=30, help="画素差のしきい値 0-255（既定: 30）")
    p.add_argument("--change-ratio", type=float, default=0.03, help="変化した画素の割合のしきい値（既定: 0.03）")
    p.add_argument("--out", default=None, help="CSV の保存先。既定: results/<モード>_<日時>.csv")
    args = p.parse_args()

    if args.mode == "latency":
        run_latency(args)
    else:
        run_detect(args, args.mode)


if __name__ == "__main__":
    main()
