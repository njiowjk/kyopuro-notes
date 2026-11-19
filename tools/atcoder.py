"""Parse and normalize the AtCoder URLs stored in the inbox."""

import re
from urllib.parse import urlsplit


ATCODER_ID = r"[A-Za-z0-9][A-Za-z0-9_-]*"
ATCODER_PATH = re.compile(
    rf"/contests/(?P<contest_id>{ATCODER_ID})/"
    rf"(?:submissions/(?P<submission_id>[0-9]+)|tasks/(?P<task_id>{ATCODER_ID}))/?"
)


class InvalidURL(ValueError):
    """An invalid or unsupported AtCoder URL."""


def parse_url(value):
    if not isinstance(value, str):
        raise InvalidURL("URLは文字列で指定してください。")
    url = value.strip()
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url):
        raise InvalidURL("URLの途中に空白または制御文字があります。")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
    except ValueError as error:
        raise InvalidURL("URLの形式が正しくありません。") from error
    if parsed.scheme != "https" or hostname != "atcoder.jp":
        raise InvalidURL("atcoder.jp のHTTPS URLを指定してください。")
    if parsed.username is not None or parsed.password is not None:
        raise InvalidURL("ユーザー情報を含むURLは登録できません。")
    if parsed.netloc.lower() not in ("atcoder.jp", "atcoder.jp:443"):
        raise InvalidURL("ポートを指定する場合は443を使ってください。")

    match = ATCODER_PATH.fullmatch(parsed.path)
    if match is None:
        raise InvalidURL("AtCoderの提出URL（提出IDは数字）か問題URLを指定してください。")
    ids = match.groupdict()
    return {
        "kind": "submission" if ids["submission_id"] is not None else "problem",
        "url": "https://atcoder.jp" + parsed.path.removesuffix("/"),
        **ids,
    }
