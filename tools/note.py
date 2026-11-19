"""Register AtCoder URLs in the local Obsidian inbox."""

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit


VAULT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
ATCODER_ID = r"[A-Za-z0-9][A-Za-z0-9_-]*"
ATCODER_PATH = re.compile(
    rf"/contests/(?P<contest_id>{ATCODER_ID})/"
    rf"(?:submissions/(?P<submission_id>[0-9]+)|tasks/(?P<task_id>{ATCODER_ID}))/?"
)


class InboxError(Exception):
    """An input or inbox error that can be shown without a traceback."""


def parse_url(value):
    if not isinstance(value, str):
        raise InboxError("URLは文字列で指定してください。")
    url = value.strip()
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url):
        raise InboxError("URLの途中に空白または制御文字があります。")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
    except ValueError as error:
        raise InboxError("URLの形式が正しくありません。") from error
    if parsed.scheme != "https" or hostname != "atcoder.jp":
        raise InboxError("atcoder.jp のHTTPS URLを指定してください。")
    if parsed.username is not None or parsed.password is not None:
        raise InboxError("ユーザー情報を含むURLは登録できません。")
    if parsed.netloc.lower() not in ("atcoder.jp", "atcoder.jp:443"):
        raise InboxError("ポートを指定する場合は443を使ってください。")

    match = ATCODER_PATH.fullmatch(parsed.path)
    if match is None:
        raise InboxError("AtCoderの提出URL（提出IDは数字）か問題URLを指定してください。")
    ids = match.groupdict()
    return {
        "kind": "submission" if ids["submission_id"] is not None else "problem",
        "url": "https://atcoder.jp" + parsed.path.removesuffix("/"),
        **ids,
    }


def read_record(line):
    record = json.loads(line.decode("utf-8"))
    if not isinstance(record, dict):
        raise InboxError("1行にはJSONオブジェクトを1件記録してください。")
    legacy = record.keys() == {"kind", "url", "registered_at"}
    version = record.get("schema_version")
    if not legacy and (type(version) is not int or version != SCHEMA_VERSION):
        raise InboxError("サポートしていないスキーマバージョンです。")

    fields = parse_url(record.get("url"))
    if record.get("kind") != fields["kind"]:
        raise InboxError("URLと種別が一致していません。")
    try:
        timestamp = datetime.fromisoformat(record.get("registered_at"))
    except (TypeError, ValueError) as error:
        raise InboxError("登録日時の形式が正しくありません。") from error
    if timestamp.utcoffset() is None:
        raise InboxError("登録日時にタイムゾーンが必要です。")
    if legacy:
        return {
            "schema_version": SCHEMA_VERSION,
            **fields,
            "registered_at": record["registered_at"],
            "status": "pending",
        }

    if not fields.keys() <= record.keys() or any(
        record[key] != fields[key] for key in ("url", "contest_id", "submission_id")
    ):
        raise InboxError("URLと識別子が一致していません。")
    task_id = record["task_id"]
    if task_id is not None and (
        not isinstance(task_id, str) or not re.fullmatch(ATCODER_ID, task_id)
    ):
        raise InboxError("task IDの形式が正しくありません。")
    if fields["kind"] == "problem" and task_id != fields["task_id"]:
        raise InboxError("問題URLとtask IDが一致していません。")
    if record.get("status") not in ("pending", "organized"):
        raise InboxError("整理状態が正しくありません。")
    return record


def read_records(path):
    if path.is_symlink():
        raise InboxError("原本には通常のファイルを使ってください。")
    try:
        source = path.open("rb")
    except FileNotFoundError:
        return []
    records = []
    with source:
        for number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                records.append(read_record(line))
            except (InboxError, ValueError) as error:
                reason = str(error) if isinstance(error, InboxError) else "JSONまたはUTF-8が不正です。"
                raise InboxError(f".local/inbox.jsonl の{number}行目: {reason}") from error
    return records


def format_entry(record):
    submission_id = record["submission_id"]
    task_id = record["task_id"]
    label = "提出" if submission_id is not None else "問題"
    submission = f"`{submission_id}`" if submission_id is not None else "—"
    task = f"`{task_id}`" if task_id is not None else "未解決"
    timestamp = datetime.fromisoformat(record["registered_at"]).isoformat()
    return (
        f"| [{label}]({record['url']}) | `{record['contest_id']}` | "
        f"{submission} | {task} | {timestamp} | 未整理 |"
    )


def render_inbox(records):
    rows = [format_entry(record) for record in records if record["status"] == "pending"]
    if not rows:
        return "# Inbox\n\n未整理のURLはありません。\n"
    return "\n".join(
        [
            "# Inbox",
            "",
            "| AtCoder | コンテストID | 提出ID | task ID | 登録日時 | 整理状態 |",
            "| --- | --- | --- | --- | --- | --- |",
            *rows,
            "",
        ]
    )


def atomic_write(path, content, local):
    # Keep partial writes in the Git-ignored directory, including for Inbox.md.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=local, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_command(args):
    fields = parse_url(args.url) if args.command == "add" else None
    local = VAULT / ".local"
    source = local / "inbox.jsonl"
    if local.is_symlink():
        raise InboxError(".local にはVault内のディレクトリを使ってください。")
    if args.command == "list":
        print(render_inbox(read_records(source)), end="")
        return

    local.mkdir(mode=0o700, exist_ok=True)
    # Lock a separate file so the lock survives replacement of the JSONL file.
    with (local / "inbox.lock").open("ab") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        records = read_records(source)
        added = fields is not None and all(record["url"] != fields["url"] for record in records)
        if added:
            records.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    **fields,
                    "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "status": "pending",
                }
            )
            atomic_write(source, "".join(json.dumps(record) + "\n" for record in records), local)

        view = "<!-- 生成元 .local/inbox.jsonl。再生成は python3 tools/note.py rebuild -->\n\n"
        try:
            atomic_write(VAULT / "Inbox.md", view + render_inbox(records), local)
        except OSError as error:
            saved = "原本にURLは保存されています。" if added else ""
            raise InboxError(
                f"Inbox.mdを更新できません。{saved} 原因を解消して rebuild を実行してください。"
                f"（{error.strerror or error}）"
            ) from error

    if args.command == "rebuild":
        print("Inbox.mdを再生成しました。")
    elif added:
        print("URLを登録し、Inbox.mdを更新しました。")
    else:
        print("このURLは登録済みです。Inbox.mdを更新しました。")


def main():
    parser = argparse.ArgumentParser(description="AtCoderのURLをローカルのInboxで管理します。")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("add", help="AtCoderの提出URLまたは問題URLを登録").add_argument("url")
    commands.add_parser("list", help="未整理URLの一覧を表示")
    commands.add_parser("rebuild", help="Inbox.mdを原本から再生成")
    args = parser.parse_args()
    try:
        run_command(args)
    except (InboxError, OSError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
