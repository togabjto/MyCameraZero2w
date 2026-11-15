# デバッグ用ツール（tools/）

監視本体（`src/`）とは別のデバッグ用ツール。どちらも標準ライブラリ（と `picamera2`）だけで動く。

## 共通の注意

- パスワード必須（`--password` か環境変数 `TOOLS_PASSWORD`）。
- 通信は HTTP（暗号化されない）。**LAN の中だけで使い、ルーターのポート開放はしない。**
- 映像は個人情報なので、使い終わったら Ctrl+C で止める。

## 録画ビューア（`tools/viewer.py`）

録画フォルダの MP4 を一覧にして、ブラウザで再生する（再生・一時停止・10 秒とばし・倍速）。
監視と同時に使える。

```
TOOLS_PASSWORD=xxxx python3 tools/viewer.py --dir movie
# ブラウザで http://<Pi の IP>:8000/ （ユーザー名: admin）
```

- 配るのは `--dir` 直下の `*.mp4` だけ（読み取り専用）。
- シークに必要な Range リクエストに対応している。

## 画角の確認（`tools/preview.py`）

カメラのライブ映像を、ブラウザに流す。設置時の画角合わせ用。

```
# 先に監視（surveillance.py）を止める
TOOLS_PASSWORD=xxxx python3 tools/preview.py
# ブラウザで http://<Pi の IP>:8001/
```

- **監視と同時には使えない**（カメラは 1 つのプログラムしか使えない）。
- 確認が終わったら Ctrl+C で止めて、監視を再開する。

## 監視しながらのライブ映像（`src/surveillance.py --live-port`）

`tools/preview.py` は、監視を止めて使うもの。**監視を動かしたまま映像を見たい場合は、こちら**を使う。

```
TOOLS_PASSWORD=xxxx python3 src/surveillance.py --live-port 8002
# ブラウザで http://<Pi の IP>:8002/ （ユーザー名: admin）
```

- 既定では配信しない（`--live-port` を付けたときだけ動く）。
- 映像は、検知に使っている **320x240・白黒**の映像（高画質ではない）。
- 画面に、「録画中」「待機中」の状態が出る。
- JPEG への変換は、**閲覧している接続があるときだけ**行う。
- パスワード必須。LAN の中だけで使う（HTTP のため暗号化されない）。
- `python3-pil`（Pillow）が必要（`sudo apt install python3-pil`。`python3-picamera2` と一緒に入っていることが多い）。
- カメラの再起動（録画停止のたびに行う回避策）の間は、映像が一瞬止まる。

## 動作確認の状況

| 項目 | 状況 |
|---|---|
| viewer の認証・Range・パス攻撃への耐性 | Mac 上で curl により確認済み |
| preview の認証・MJPEG の配信形式 | Mac 上で偽フレームにより確認済み |
| ライブ配信（`--live-port`）の認証・ステータス・JPEG の中身（320x240・白黒） | Mac 上で偽フレームにより確認済み |
| ライブ配信: 閲覧者がいない間は JPEG 変換をしない | Mac 上で確認済み（2 秒間で 0 回） |
| ライブ配信: 録画の動作が変わらないこと | Mac 上で偽のカメラにより確認済み（実機は TODO） |
| ライブ配信: 実機での映像表示 | TODO: 実機で未確認 |
| ライブ配信: 閲覧中の CPU・メモリ（`fps` など） | TODO: 未計測 |
| viewer をブラウザで再生・10 秒とばし・倍速 | 実機（Pi Zero 2 W）と Mac のブラウザで確認済み（本人の報告） |
| preview の実カメラ映像 | TODO: 実機で未確認 |
| preview 使用中の CPU・メモリ | TODO: 未計測 |
