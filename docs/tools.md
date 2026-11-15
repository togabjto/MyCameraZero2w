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

## 動作確認の状況

| 項目 | 状況 |
|---|---|
| viewer の認証・Range・パス攻撃への耐性 | Mac 上で curl により確認済み |
| preview の認証・MJPEG の配信形式 | Mac 上で偽フレームにより確認済み |
| viewer をブラウザで再生・シーク・倍速 | TODO: 実機で未確認 |
| preview の実カメラ映像 | TODO: 実機で未確認 |
| preview 使用中の CPU・メモリ | TODO: 未計測 |
