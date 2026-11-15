"""動いているプロセスの CPU・メモリを、一定間隔で CSV に記録する。

用途: 実際の監視（src/surveillance.py）を長時間（例: 24 時間）動かして、
      メモリが増え続けていないか（メモリリークの有無）を確かめる。

使い方（Pi 上で、2 つのターミナルを使う）:
    # ターミナル 1: 監視を起動
    python3 -u src/surveillance.py
    # ターミナル 2: その PID を記録（60 秒ごと）
    python3 tools/sample_process.py --pid $(pgrep -f surveillance.py | head -1) --interval 60

プロセスが終了するか、--duration 秒が経つか、Ctrl+C で止まる。
CSV は 1 行ごとに書き出すので、途中で止まっても、そこまでの記録は残る。

記録する列:
  elapsed_s        開始からの経過秒
  cpu_process_pct  対象プロセスの CPU 使用率（1 コア使い切りで 100%。複数コアなら 100% を超える）
  cpu_system_pct   機械全体の CPU 使用率（全コア平均。最大 100%）
  rss_kb           対象プロセスの実メモリ使用量（VmRSS）
  mem_available_kb 機械全体で、まだ使えるメモリ（MemAvailable）
  throttled        vcgencmd get_throttled の値（0x0 なら電圧不足などなし。使えなければ空）

注意: 録画（ffmpeg の変換など）は別プロセスなので、この記録には含まれない。
      機械全体の値は cpu_system_pct と mem_available_kb で見る。
"""
import argparse
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _metrics import CsvLog, Sampler  # noqa: E402

COLUMNS = ["timestamp", "elapsed_s", "pid", "cpu_process_pct", "cpu_system_pct",
           "rss_kb", "mem_available_kb", "throttled"]


def main():
    p = argparse.ArgumentParser(description="プロセスの CPU・メモリを CSV に記録する")
    p.add_argument("--pid", type=int, required=True, help="記録するプロセスの PID")
    p.add_argument("--interval", type=float, default=60.0, help="記録の間隔（秒）。既定: 60")
    p.add_argument("--duration", type=float, default=0, help="記録する長さ（秒）。0 なら、止めるまで")
    p.add_argument("--out", default=None, help="CSV の保存先。既定: results/process_<日時>.csv")
    args = p.parse_args()

    if not os.path.exists(f"/proc/{args.pid}"):
        sys.exit(f"エラー: PID {args.pid} のプロセスが見つかりません。")
    out = args.out or f"results/process_{datetime.now():%Y%m%d_%H%M%S}.csv"
    log = CsvLog(out, COLUMNS)
    sampler = Sampler(args.pid)
    start = time.monotonic()
    print(f"[sample] PID {args.pid} を {args.interval:g} 秒ごとに記録 → {out}（Ctrl+C で終了）", flush=True)
    try:
        while True:
            time.sleep(args.interval)
            if not os.path.exists(f"/proc/{args.pid}"):
                print("[sample] 対象のプロセスが終了しました。")
                break
            row = sampler.sample()
            row.update(timestamp=datetime.now().isoformat(timespec="seconds"),
                       elapsed_s=round(time.monotonic() - start, 1), pid=args.pid)
            log.write(row)
            print(f"[sample] {row['elapsed_s']:>8.0f}s  cpu(proc)={row['cpu_process_pct']}%  "
                  f"cpu(sys)={row['cpu_system_pct']}%  rss={row['rss_kb']}kB  throttled={row['throttled']}", flush=True)
            if args.duration and time.monotonic() - start >= args.duration:
                break
    except (KeyboardInterrupt, FileNotFoundError):
        print("\n[sample] 終了します。")
    finally:
        log.close()
    print(f"[sample] 保存しました: {out}")


if __name__ == "__main__":
    main()
