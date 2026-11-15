# カメラが固まる問題の調査手順

## 現状（分かっていること）

- `src/surveillance.py` は、録画を止めるたびに `picam2.stop()` → `time.sleep(0.5)` → `picam2.start()` でカメラを再起動している（回避策）。
- コード内のコメントによると、これをしないとカメラが固まることがあった。
  固まる場所は、コメント上は `capture_array("lores")` の付近とされているが、確認はしていない（TODO: 実機で確認）。
- **原因は分かっていない。原因が分かるまで、回避策は消さない。**

以下の「仮説」は、まだ確かめていない推測であり、結論ではない。

## 仮説（未検証）

| # | 仮説 | 確かめ方 |
|---|---|---|
| 1 | `stop_recording()` のあと、`lores` ストリームのバッファが戻らなくなる | 手順 B の「再起動なし」で再現させ、固まった時の libcamera ログを見る |
| 2 | エンコーダを毎回作り直すことが関係している（Picamera2 側の挙動） | エンコーダを 1 つ使い回す版と比べる |
| 3 | メモリ（特にカメラ用バッファ）の不足 | 固まる直前の `free -m` と、`/proc/meminfo` の CMA 関連の値を記録する |
| 4 | 電圧不足や負荷によるもの | `vcgencmd get_throttled` を記録する（検証時は `0x0` だった） |

## 手順 A：ログの取り方

固まった時に原因を追えるよう、実行前に次を用意する。

1. 別のターミナルで、電源状態とメモリを 5 秒ごとに記録する（ファイル名は日時入り）。
   ```
   while true; do
     echo "$(date +%T) $(vcgencmd get_throttled) $(free -m | awk 'NR==2{print "used="$3"MB free="$4"MB"}')"
     sleep 5
   done | tee freeze_watch_$(date +%Y%m%d_%H%M%S).log
   ```
2. libcamera の詳細ログを有効にして、監視を実行する。
   ```
   LIBCAMERA_LOG_LEVELS='*:DEBUG' python3 -u src/surveillance.py 2>&1 | tee freeze_run_$(date +%Y%m%d_%H%M%S).log
   ```
   ログは大きくなるので、短い時間で試す。
3. 固まったと思ったら、別のターミナルから、Python が何をしているか確認する。
   ```
   top -b -n 1 | head -15
   ```
   - CPU がほぼ 0% なら、どこかで待ち続けている（デッドロックの疑い）。
   - CPU が高いなら、ループや処理の詰まり。
4. カーネルのメッセージも、固まったあとに保存する（カメラやメモリのエラーが出ていないか）。
   ```
   sudo dmesg | tail -100 > freeze_dmesg_$(date +%Y%m%d_%H%M%S).log
   ```
5. Python のどの行で止まっているかを知りたい場合は、`surveillance.py` の先頭に、次の 2 行を足した**コピー**で実行する（本体は変更しない）。
   ```
   import faulthandler
   faulthandler.dump_traceback_later(30, repeat=True)  # 30 秒ごとに、全スレッドの位置を出力
   ```

## 手順 B：再起動なしで再現させる条件

回避策を外した状態で、固まるかを調べる。**本体は変更せず、コピーで行う。**

1. `src/surveillance.py` を、リポジトリの外（例：`~/freeze_test.py`）にコピーする。
   `libmotion.so` の読み込み場所が変わるので、`LIB_PATH` を、`src/libmotion.so` の絶対パスに書き換える。
2. コピーの中で、`[DEBUG] Resetting camera pipeline` の下の、次の 3 行をコメントアウトする。
   ```
   picam2.stop()
   time.sleep(0.5)
   picam2.start()
   ```
3. 実行して、次を繰り返す。
   - カメラの前で動く → 録画が始まる → 動きをやめて 10 秒待つ → `[STOP]` が出る。
4. 記録すること：
   - **何回目の録画の後で固まったか**（毎回か、数回に 1 回か）。
   - 固まる直前の最後のログの行。
   - 手順 A のログ（電圧・メモリ）。
5. 条件を変えて、同じ試行をする（条件ごとに、回数と固まった回を表にする）。
   - 録画の長さを変える（動きの継続時間を短く／長く）。
   - `time.sleep(0.5)` だけを残す（再起動はしない）。
   - エンコーダを使い回す。

## 記録の書式

| 試行 | 条件 | 録画回数 | 固まった回 | 最後のログ | `throttled` |
|---|---|---|---|---|---|
| 1 | 再起動なし | TODO | TODO | TODO | TODO |

## 結果（本人が実機で記入）

TODO: 原因の特定、または「再現しなかった」の記録。
