# 計測の手順（実機の Pi Zero 2 W で実行する）

**ここに書く数値は、実機で測った値だけにする。** 測っていない欄は `TODO: 実測値` のまま残す。
結果の CSV は `results/` に保存される。測った CSV は、証拠としてそのままコミットしてよい。

## 準備

```
cd ~/MyCameraZero2w
git pull
make -C src                    # libmotion.so をビルド
```

- 監視（`surveillance.py`）や `tools/preview.py` は、止めておく（カメラは 1 つのプログラムしか使えない）。
- 計測の前に、条件を記録する（結果の表に書く）。
  ```
  uname -a; cat /etc/os-release | head -2
  vcgencmd measure_temp          # 温度（高いと CPU が制限されることがある）
  vcgencmd get_throttled         # 0x0 なら電圧不足などなし
  ```
- 比べるときは、**部屋の明るさ・カメラの向き・電源・時間をそろえ、画面は動かさない**（静止状態）。

## 1. CPU 使用率・メモリ・処理速度（2 系統に分けた効果）

同じ条件で、本システムの構成（検知用 320x240）と、比較用（フル HD をそのまま CPU で検知）を測る。

```
python3 tools/benchmark.py detect --duration 60
python3 tools/benchmark.py fullhd --duration 60
# 録画（H.264 エンコード）をしながら測る場合（実際の運用に近い）
python3 tools/benchmark.py detect --duration 60 --record
python3 tools/benchmark.py fullhd --duration 60 --record
```

- 1 秒ごとに、CSV へ記録する。終了時に、平均・最大が表示される。
- `--sleep 0` を付けると、待ちなしで、処理速度の上限（fps）が測れる。既定は 0.05 秒で、`surveillance.py` と同じ。
- 見る列:
  - `fps`: 検知ループの処理速度
  - `avg_capture_ms`: カメラから 1 フレーム取るのにかかった時間
  - `avg_detect_ms`: C の差分処理にかかった時間（2 系統の効果は、ここに出るはず）
  - `cpu_process_pct`: このプロセスの CPU 使用率（100% = 1 コア使い切り。複数コアなら 100% を超える）
  - `cpu_system_pct`: 機械全体の CPU 使用率（最大 100%）
  - `rss_kb`: 実メモリ使用量
- 測定中に、静止状態のまま、動きがないか確認する（`motion_count` が 0 のはず。0 でなければ、ノイズや揺れがある）。

## 2. 動きが起きてから録画が始まるまでの時間

```
python3 tools/benchmark.py latency --trials 5
```

指示が出たら、カメラの前で動く。5 回分が記録される。

- `detect_to_record_call_ms`: 検知 → `start_recording()` が戻るまで
- `detect_to_first_frame_ms`: 検知 → エンコーダから最初のフレームが出るまで

**限界（正直に書くこと）:** このツールが測れるのは、**「検知した瞬間」から**の時間。
実際に動き始めてから検知されるまでの遅れ（フレーム間隔、差分の判定にかかる時間）は含まれない。
動き始めからの時間が必要なら、外部の基準（例: 画面に時刻を表示してスマホで撮る）で、別に測る。

## 3. 長時間（例: 24 時間）のメモリ推移

実際の監視を動かして、メモリが増え続けていないか（メモリリークの有無）を見る。

```
# ターミナル 1
python3 -u src/surveillance.py
# ターミナル 2（60 秒ごとに記録。24 時間 = 86400 秒）
python3 tools/sample_process.py --pid $(pgrep -f surveillance.py | head -1) --interval 60 --duration 86400
```

- 見る列: `rss_kb`（このプロセス）と `mem_available_kb`（機械全体の空き）の**時間に対する傾き**。
  録画の直後などで一時的に増減するのは普通。**長時間で右肩上がりが続くか**を見る。
- `throttled` が `0x0` のままかも確認する。
- 録画の変換（`ffmpeg`）は別プロセス。機械全体の影響は `cpu_system_pct` と `mem_available_kb` で見る。
- 長時間の実行は、SSH が切れても止まらないように `tmux` などの中で動かすとよい（`sudo apt install tmux`）。

## 4. しきい値を変えて試す

```
python3 src/surveillance.py --pixel-threshold 40 --change-ratio 0.05
python3 tools/benchmark.py detect --duration 60 --pixel-threshold 20 --change-ratio 0.01
```

- 既定値は `--pixel-threshold 30`（0〜255）、`--change-ratio 0.03`（0 より大きく 1 以下）。
- 低くするほど敏感で、誤検知が増える。高くするほど、小さい動きを見逃す。
- 試すときは、「静止状態で誤検知が出るか」「小さい動き（指だけなど）が検知されるか」を、条件ごとに表にする。

## 結果

### 測定条件

| 項目 | 内容 |
|---|---|
| 日付 | TODO |
| OS / カーネル | TODO |
| 温度（開始時） | TODO |
| 電源 | TODO |
| `get_throttled` | TODO |

### 2 系統に分けた効果（静止状態・60 秒）

| 構成 | fps | CPU（プロセス）平均 / 最大 | CPU（機械全体）平均 | RSS | 1 回の差分処理 |
|---|---|---|---|---|---|
| 検知用 320x240（本システム） | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 |
| フル HD を CPU で検知 | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 |
| 検知用 320x240 + 録画 | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 |
| フル HD を CPU で検知 + 録画 | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 |

### 検知から録画開始まで（n = 5）

| 項目 | 平均 | 最小 | 最大 |
|---|---|---|---|
| 検知 → `start_recording()` が戻る | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 |
| 検知 → 最初のフレーム | TODO: 実測値 | TODO: 実測値 | TODO: 実測値 |

### 長時間のメモリ推移

| 項目 | 内容 |
|---|---|
| 実行時間 | TODO: 実測値 |
| 録画の回数 | TODO: 実測値 |
| RSS の最初 → 最後 | TODO: 実測値 |
| 傾き（増え続けているか） | TODO: 実測値 |

## 計測ツール自体の確認状況

| 項目 | 状況 |
|---|---|
| `/proc` の読み取り（CPU・メモリ）の変換処理 | Mac 上で、実際の形式の文字列を使って確認済み |
| `benchmark.py` の 3 モード、CSV 出力、まとめの表示 | Mac 上で、偽のカメラ・偽の `/proc` により、流れを確認済み |
| 実機での動作 | TODO: 未確認（実機で最初に実行して、エラーがないか確認する） |
| `capture_array` の配列の形（`[:h, :w]` で Y プレーンを取れるか） | TODO: 実機で未確認。フル HD の YUV420 は、行数が 1.5 倍の配列になる想定 |
