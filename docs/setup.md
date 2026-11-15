# セットアップ手順（Raspberry Pi Zero 2 W）

ステップ 5 の README に転記するための下書き。

## 動作を確認した環境

- Raspberry Pi Zero 2 W（`uname -m` は `armv7l`＝32bit OS、bookworm 系）
- Camera Module 3 NoIR（`rpicam-hello --list-cameras` で `imx708_noir` と表示）

## 必要なパッケージ

| パッケージ | 用途 | 備考 |
|---|---|---|
| `python3-picamera2` | カメラの制御・H.264 エンコーダ | 画面表示用のパッケージを避けるため `--no-install-recommends` を付ける |
| `python3-numpy` | 画像（配列）の受け渡し | |
| `ffmpeg` | H.264 → MP4 の詰め替え（`-c copy`） | |
| `gcc` | `libmotion.so` のビルド | 検証時の環境には入っていた |
| `make` | ビルド | TODO: Pi に入っているか未確認 |
| `git` | リポジトリの取得 | 検証時の環境には入っていた |

```
sudo apt update
sudo apt install -y --no-install-recommends python3-picamera2 python3-numpy ffmpeg gcc make git
```

## ビルドと実行

```
git clone https://github.com/togabjto/MyCameraZero2w
cd MyCameraZero2w/src
make
python3 surveillance.py
```

- `libmotion.so` は `surveillance.py` と同じフォルダから読み込む。
- 録画データ（`movie/`）と一時ファイル（`temp_XXXX.h264`）は、実行したフォルダに作られる。
  TODO: 保存先を固定するか検討する。
- 止めるときは Ctrl+C。

## つまずいたところ

- 画面表示用（Qt など）の大きなパッケージまで入って、ダウンロードに時間がかかった。`--no-install-recommends` で避けられる。
- 電源の電圧不足やファイルシステムの破損が疑われる症状（`Input/output error`）が出た。
  録画中は `vcgencmd get_throttled` で `0x0`（電圧不足なし）を確認できる。
