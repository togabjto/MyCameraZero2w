"""tools/ の簡易サーバー共通の認証処理（Basic 認証）。

注意: Basic 認証は通信が暗号化されない（HTTP）。LAN の中だけで使い、
      ルーターのポート開放でインターネットに公開しないこと。
"""
import argparse
import base64
import hmac
import os
import sys


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="0.0.0.0", help="待ち受けアドレス（既定: 0.0.0.0）")
    parser.add_argument("--port", type=int, default=8000, help="ポート番号（既定: 8000）")
    parser.add_argument("--user", default="admin", help="ユーザー名（既定: admin）")
    parser.add_argument(
        "--password",
        default=os.environ.get("TOOLS_PASSWORD"),
        help="パスワード（環境変数 TOOLS_PASSWORD でも指定できる。必須）",
    )


def require_password(args: argparse.Namespace) -> None:
    """パスワードなしでの起動を拒否する（映像は個人情報のため）。"""
    if not args.password:
        sys.exit("エラー: パスワードが未指定です。--password か環境変数 TOOLS_PASSWORD を設定してください。")


def is_authorized(header_value: str | None, user: str, password: str) -> bool:
    """Authorization ヘッダーが正しいかを、定数時間で比較して判定する。"""
    if not header_value or not header_value.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header_value[6:], validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    given_user, sep, given_password = decoded.partition(":")
    if not sep:
        return False
    ok_user = hmac.compare_digest(given_user.encode(), user.encode())
    ok_pass = hmac.compare_digest(given_password.encode(), password.encode())
    return ok_user and ok_pass
