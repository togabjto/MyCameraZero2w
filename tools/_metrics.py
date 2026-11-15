"""計測ツール共通の処理: /proc から CPU・メモリを読み、CSV に書く（外部ライブラリ不要）。

Linux（Raspberry Pi OS）専用。/proc の読み取り部分は、文字列を受け取る関数に分けてある。
"""
import csv
import os
import shutil
import subprocess
import time

CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


# ---------- /proc の文字列を読む（テストしやすいよう、純粋な関数にしてある） ----------
def parse_process_ticks(stat_text: str) -> int:
    """/proc/<pid>/stat の内容から、utime + stime（クロック刻み）を返す。
    プロセス名に空白や ')' が含まれても読めるよう、最後の ')' の後ろから数える。"""
    after = stat_text[stat_text.rindex(")") + 2:].split()
    # after[0] は state（全体の 3 番目の項目）。utime は 14 番目、stime は 15 番目。
    return int(after[11]) + int(after[12])


def parse_system_cpu(stat_text: str):
    """/proc/stat の先頭行から (全体, 待機) の刻み数を返す。待機は idle + iowait。"""
    fields = [int(x) for x in stat_text.splitlines()[0].split()[1:]]
    total = sum(fields[:8])  # user nice system idle iowait irq softirq steal
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    return total, idle


def parse_kb(text: str, key: str):
    """'/proc/<pid>/status' や '/proc/meminfo' から 'Key:   123 kB' の数値を返す。なければ None。"""
    for line in text.splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1])
    return None


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def read_throttled():
    """vcgencmd get_throttled の値（例 '0x0'）。使えなければ空文字。"""
    if shutil.which("vcgencmd") is None:
        return ""
    try:
        out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=2).stdout
        return out.strip().split("=")[-1]
    except Exception:
        return ""


class Sampler:
    """sample() を呼ぶたびに、前回からの CPU 使用率とメモリを返す。"""

    def __init__(self, pid: int, with_throttled: bool = True):
        self.pid = pid
        # vcgencmd は外部コマンドを起動するので、短い間隔の計測では呼ばない（計測自体が負荷になる）
        self.with_throttled = with_throttled
        self._t = time.monotonic()
        self._proc_ticks = parse_process_ticks(_read(f"/proc/{pid}/stat"))
        self._sys_total, self._sys_idle = parse_system_cpu(_read("/proc/stat"))

    def sample(self) -> dict:
        now = time.monotonic()
        proc_ticks = parse_process_ticks(_read(f"/proc/{self.pid}/stat"))
        sys_total, sys_idle = parse_system_cpu(_read("/proc/stat"))
        dt = now - self._t
        d_total = sys_total - self._sys_total
        result = {
            # 対象プロセスが使った CPU 時間 ÷ 経過時間（1 コア使い切りで 100%、4 コアなら最大 400%）
            "cpu_process_pct": round((proc_ticks - self._proc_ticks) / CLK_TCK / dt * 100, 1) if dt > 0 else 0.0,
            # 機械全体の CPU 使用率（全コア平均。最大 100%）
            "cpu_system_pct": round((1 - (sys_idle - self._sys_idle) / d_total) * 100, 1) if d_total > 0 else 0.0,
            "rss_kb": parse_kb(_read(f"/proc/{self.pid}/status"), "VmRSS"),
            "mem_available_kb": parse_kb(_read("/proc/meminfo"), "MemAvailable"),
            "throttled": read_throttled() if self.with_throttled else "",
        }
        self._t, self._proc_ticks, self._sys_total, self._sys_idle = now, proc_ticks, sys_total, sys_idle
        return result


class CsvLog:
    """1 行ごとに書き出して flush する CSV（長時間の計測が途中で止まっても、そこまでが残る）。"""

    def __init__(self, path: str, columns: list):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.columns = columns
        self._f = open(path, "w", newline="", encoding="utf-8")
        self._w = csv.DictWriter(self._f, fieldnames=columns)
        self._w.writeheader()
        self._f.flush()

    def write(self, row: dict):
        self._w.writerow({c: row.get(c, "") for c in self.columns})
        self._f.flush()

    def close(self):
        self._f.close()
