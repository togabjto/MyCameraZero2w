"""カメラの向き（回転・反転）の設定。

カメラの ISP（ハードウェア）で上下・左右を反転して実現するので、CPU の負荷は増えない。
Raspberry Pi の ISP が対応するのは、上下・左右の反転だけ。
そのため、回転は 0° と 180°（上下・左右の両方を反転）のみ。90° / 270° には対応しない。
"""
import argparse

ROTATIONS = (0, 180)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--rotation", type=int, choices=ROTATIONS, default=0,
                        help="カメラの向き（度）。0 または 180（上下逆さまに設置したときは 180）。既定: 0")
    parser.add_argument("--hflip", action="store_true", help="左右を反転する")
    parser.add_argument("--vflip", action="store_true", help="上下を反転する")


def flips(rotation: int, hflip: bool, vflip: bool):
    """回転と反転の指定から、実際にかける (左右反転, 上下反転) を返す。
    180° は「左右と上下の両方を反転」と同じ。さらに反転を指定すると、その分が打ち消し合う。"""
    if rotation not in ROTATIONS:
        raise ValueError(f"rotation は {ROTATIONS} のどちらかです: {rotation}")
    rotated = rotation == 180
    return rotated != bool(hflip), rotated != bool(vflip)


def make_transform(rotation: int, hflip: bool, vflip: bool):
    """Picamera2 の設定に渡す Transform を返す。反転が不要なら None（設定に何も渡さない）。"""
    h, v = flips(rotation, hflip, vflip)
    if not (h or v):
        return None
    from libcamera import Transform   # Pi 上でのみ必要なので、必要なときだけ読み込む
    return Transform(hflip=int(h), vflip=int(v))


def describe(rotation: int, hflip: bool, vflip: bool) -> str:
    h, v = flips(rotation, hflip, vflip)
    return f"rotation={rotation} hflip={int(bool(hflip))} vflip={int(bool(vflip))} （実際にかける反転: 左右={int(h)} 上下={int(v)}）"
