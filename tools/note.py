"""Register AtCoder problems and locate their local source in an Obsidian vault."""

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

from atc_source import (
    ERROR_LABELS, EXTENSIONS, MAX_SOURCE_BYTES, SourceError, fetch_source, is_problem_index,
)
from atcoder import ATCODER_ID, InvalidURL, parse_url

if os.name == "nt":
    import msvcrt
else:
    import fcntl


VAULT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
STATUS_LABELS = {
    "pending": "取得待ち",
    "resolved": "ローカルソース照合済み",
    "organized": "整理済み",
    "blocked": "保留",
}
LOCAL_ERROR_LABELS = {
    "task_conflict": "同じtask IDに異なる問題URLが登録されている",
    "source_changed": "ソースの内容または言語が変わったため保留。確認後に `--accept-source-change`",
    "snapshot_conflict": "保存済みソースの種類またはSHA-256が一致しない",
    "storage_error": "ローカルスナップショットを保存できない",
}


class InboxError(Exception):
    """An inbox error safe to display without a traceback."""


@dataclass
class Inbox:
    records: list
    lines: list
    indices: list


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
    except (TypeError, ValueError):
        raise InboxError("登録日時の形式が正しくありません。") from None
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
    if record.get("status") not in tuple(STATUS_LABELS):
        raise InboxError("整理状態が正しくありません。")
    target = record.get("problem_url")
    if target is not None:
        problem = parse_url(target)
        if (
            problem["kind"] != "problem"
            or target != problem["url"]
            or task_id != problem["task_id"]
            or (fields["kind"] == "problem" and target != fields["url"])
        ):
            raise InboxError("問題URLと識別子が一致していません。")
    elif record["status"] == "resolved" and fields["kind"] == "submission":
        raise InboxError("解決済みの旧提出には問題URLが必要です。")
    reason = record.get("resolution_error")
    if reason is not None and not isinstance(reason, str):
        raise InboxError("解決エラーの形式が正しくありません。")
    snapshot = record.get("local_source")
    if snapshot is not None and (
        not isinstance(snapshot, dict)
        or snapshot.get("origin") != "atc-rs-local"
        or snapshot.get("language") not in tuple(EXTENSIONS)
        or not is_problem_index(snapshot.get("index"))
        or not isinstance(snapshot.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", snapshot["sha256"])
    ):
        raise InboxError("ローカルソースの取得記録が不正です。")
    return record


def read_inbox(path):
    if path.is_symlink():
        raise InboxError("原本には通常のファイルを使ってください。")
    try:
        with path.open("rb") as source:
            lines = source.readlines()
    except FileNotFoundError:
        lines = []
    records, indices = [], []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(read_record(line))
        except (InboxError, ValueError) as error:
            reason = str(error) if isinstance(error, (InboxError, InvalidURL)) else "JSONまたはUTF-8が不正です。"
            raise InboxError(f".local/inbox.jsonl の{index + 1}行目: {reason}") from None
        indices.append(index)
    return Inbox(records, lines, indices)


def read_records(path):
    return read_inbox(path).records


def conflict_urls(records):
    urls_by_task = {}
    for record in records:
        if record["kind"] == "problem":
            urls_by_task.setdefault(record["task_id"], set()).add(record["url"])
    return {url for urls in urls_by_task.values() if len(urls) > 1 for url in urls}


def effective_status(record):
    if record["kind"] == "problem" and record["status"] == "resolved" and not record.get("local_source"):
        return "pending"
    return record["status"]


def error_label(code):
    return LOCAL_ERROR_LABELS.get(code) or ERROR_LABELS.get(code) or ""


def render_inbox(records):
    conflicts = conflict_urls(records)
    problems = []
    legacy = []
    for record in records:
        if record["status"] == "organized":
            continue
        timestamp = datetime.fromisoformat(record["registered_at"]).isoformat()
        if record["kind"] == "submission":
            task = record["task_id"] or "—"
            legacy.append(f"| [提出]({record['url']}) | `{task}` | {timestamp} |")
            continue

        state = "blocked" if record["url"] in conflicts else effective_status(record)
        code = "task_conflict" if record["url"] in conflicts else record.get("resolution_error")
        label = STATUS_LABELS[state]
        if reason := error_label(code):
            label += f"（{reason}）"
        details = "—"
        if snapshot := record.get("local_source"):
            details = f"{snapshot['language']} / `{snapshot['sha256'][:12]}`"
            if state != "resolved":
                details += "（前回取得）"
        problems.append(
            f"| [問題]({record['url']}) | `{record['contest_id']}` | `{record['task_id']}` | "
            f"{details} | {timestamp} | {label} |"
        )
    if not problems and not legacy:
        return "# Inbox\n\n未整理のURLはありません。\n"
    lines = ["# Inbox", ""]
    if problems:
        lines.extend([
            "## 問題",
            "",
            "| AtCoder | コンテストID | task ID | 言語・SHA-256 | 登録日時 | 状態 |",
            "| --- | --- | --- | --- | --- | --- |",
            *problems,
            "",
        ])
    if legacy:
        lines.extend([
            "## 旧方式の提出URL",
            "",
            "旧登録として保持しています。ローカルソースを取得するには問題URLを登録してください。",
            "",
            "| AtCoder | task ID | 登録日時 |",
            "| --- | --- | --- |",
            *legacy,
            "",
        ])
    return "\n".join(lines)


def atomic_write(path, content, local, *, immutable=False):
    # Temporary files also stay inside the Git-ignored directory.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=local, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if immutable:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def file_lock(path):
    # Use a separate inode so replacing data never invalidates the lock.
    with path.open("ab") as lock:
        if os.name == "nt":
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def write_records(path, inbox, updated):
    lines = inbox.lines.copy()
    for old, new, index in zip(inbox.records, updated, inbox.indices):
        if new != old:
            lines[index] = (json.dumps(new) + "\n").encode("utf-8")
    extra = updated[len(inbox.records):]
    if extra and lines and not lines[-1].endswith(b"\n"):
        lines.append(b"\n")
    lines.extend((json.dumps(record) + "\n").encode("utf-8") for record in extra)
    atomic_write(path, b"".join(lines), path.parent)


def write_view(local, records, *, saved):
    view = "<!-- 生成元 .local/inbox.jsonl。再生成は python3 tools/note.py rebuild -->\n\n"
    try:
        atomic_write(VAULT / "Inbox.md", (view + render_inbox(records)).encode("utf-8"), local)
    except OSError:
        details = "原本には変更が保存されています。" if saved else ""
        raise InboxError(
            f"Inbox.mdを更新できません。{details} 原因を解消して rebuild を実行してください。"
        ) from None


def is_reparse(info):
    return bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def snapshot_path(directory, metadata):
    suffix = EXTENSIONS[metadata["language"]]
    return directory / f"{metadata['sha256']}.{suffix}"


def check_snapshot(path, digest):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode) or is_reparse(info) or info.st_size > MAX_SOURCE_BYTES:
        raise InboxError(LOCAL_ERROR_LABELS["snapshot_conflict"])
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags | getattr(os, "O_BINARY", 0)), "rb") as file:
        opened = os.fstat(file.fileno())
        if not stat.S_ISREG(opened.st_mode) or is_reparse(opened) or not os.path.samestat(info, opened):
            raise InboxError(LOCAL_ERROR_LABELS["snapshot_conflict"])
        content = file.read(MAX_SOURCE_BYTES + 1)
    if len(content) > MAX_SOURCE_BYTES or hashlib.sha256(content).hexdigest() != digest:
        raise InboxError(LOCAL_ERROR_LABELS["snapshot_conflict"])
    return True


def update_source(record, export, local, accept_change):
    metadata = {
        "origin": "atc-rs-local",
        "index": export.index,
        "language": export.language,
        "sha256": hashlib.sha256(export.content).hexdigest(),
    }
    previous = record.get("local_source")
    if previous and previous["index"] != metadata["index"]:
        return {**record, "status": "blocked", "resolution_error": "identity_mismatch"}
    directory = local / "sources"
    try:
        directory.mkdir(mode=0o700, exist_ok=True)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or is_reparse(info):
            raise InboxError(LOCAL_ERROR_LABELS["snapshot_conflict"])
        if previous:
            check_snapshot(snapshot_path(directory, previous), previous["sha256"])
            changed = any(previous[key] != metadata[key] for key in ("language", "sha256"))
            if changed and not accept_change:
                return {**record, "status": "pending", "resolution_error": "source_changed"}
        target = snapshot_path(directory, metadata)
        if not check_snapshot(target, metadata["sha256"]):
            try:
                atomic_write(target, export.content, local, immutable=True)
            except FileExistsError:
                if not check_snapshot(target, metadata["sha256"]):
                    raise OSError("snapshot disappeared before validation") from None
    except InboxError:
        return {**record, "status": "blocked", "resolution_error": "snapshot_conflict"}
    except OSError:
        return {**record, "status": "pending", "resolution_error": "storage_error"}
    updated = {**record, "status": "resolved", "local_source": metadata}
    updated.pop("resolution_error", None)
    return updated


def run_resolve(path, args):
    local = path.parent
    workspace = Path(os.path.abspath(Path(args.workspace).expanduser())) if args.workspace else Path.cwd()
    with file_lock(local / "resolve.lock"):
        records = read_records(path)
        issues = conflict_urls(records)
        outcomes = {}
        for record in records:
            url = record["url"]
            if (
                record["kind"] != "problem"
                or effective_status(record) not in ("pending", "resolved")
                or url in outcomes
                or url in issues
            ):
                continue
            try:
                outcomes[url] = fetch_source(record, workspace, args.language)
            except SourceError as error:
                outcomes[url] = error

        # Reread while holding the write lock so registrations made during atc
        # execution are retained. Publish snapshots before the JSONL references.
        with file_lock(local / "inbox.lock"):
            inbox = read_inbox(path)
            issues = conflict_urls(inbox.records)
            updated = []
            results = []
            for record in inbox.records:
                if record["kind"] != "problem" or record["status"] == "organized":
                    updated.append(record)
                    continue
                outcome = outcomes.get(record["url"])
                if record["url"] in issues:
                    record = {**record, "status": "blocked", "resolution_error": "task_conflict"}
                elif record["status"] == "blocked":
                    results.append(record)
                    updated.append(record)
                    continue
                elif isinstance(outcome, SourceError):
                    state = "blocked" if outcome.code == "identity_mismatch" else "pending"
                    record = {**record, "status": state, "resolution_error": outcome.code}
                elif outcome is not None:
                    record = update_source(record, outcome, local, args.accept_source_change)
                else:
                    updated.append(record)
                    continue
                results.append(record)
                updated.append(record)
            changed = inbox.records != updated
            if changed:
                write_records(path, inbox, updated)
            write_view(local, updated, saved=changed)

    counts = Counter(row["status"] for row in results)
    for code, count in Counter(row.get("resolution_error") for row in results if row["status"] != "resolved").items():
        print(f"{count}件（{error_label(code) or '要確認'}）")
    print(f"照合済み {counts['resolved']}件、取得待ち {counts['pending']}件、保留 {counts['blocked']}件。")
    return int(bool(counts["pending"] or counts["blocked"]))


def run_command(args):
    fields = parse_url(args.url) if args.command == "add" else None
    if fields is not None and fields["kind"] != "problem":
        raise InvalidURL("新規登録にはAtCoderの問題URL（/tasks/…）を指定してください。")
    local = VAULT / ".local"
    source = local / "inbox.jsonl"
    if local.is_symlink() or (local.exists() and is_reparse(local.lstat())):
        raise InboxError(".local にはVault内のディレクトリを使ってください。")
    if args.command == "list":
        print(render_inbox(read_records(source)), end="")
        return 0

    local.mkdir(mode=0o700, exist_ok=True)
    if args.command == "resolve":
        return run_resolve(source, args)
    with file_lock(local / "inbox.lock"):
        inbox = read_inbox(source)
        records = inbox.records
        added = fields is not None and all(record["url"] != fields["url"] for record in records)
        if added:
            record = {
                "schema_version": SCHEMA_VERSION,
                **fields,
                "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": "pending",
            }
            records = [*records, record]
            if record["url"] in conflict_urls(records):
                record.update(status="blocked", resolution_error="task_conflict")
            write_records(source, inbox, records)
        write_view(local, records, saved=added)

    if args.command == "rebuild":
        print("Inbox.mdを再生成しました。")
    elif added:
        print("問題URLを登録し、Inbox.mdを更新しました。")
    else:
        print("このURLは登録済みです。Inbox.mdを更新しました。")
    return 0


def main():
    parser = argparse.ArgumentParser(description="AtCoderの問題とローカルソースをInboxで管理します。")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("add", help="AtCoderの問題URLを登録").add_argument("url")
    resolve = commands.add_parser("resolve", help="atc-rsからローカルソースを取得")
    resolve.add_argument("--workspace", help="atc-rs Workspace root（省略時は現在のディレクトリ）")
    resolve.add_argument("--language", choices=tuple(EXTENSIONS), help="取得する言語を選択")
    resolve.add_argument("--accept-source-change", action="store_true", help="変更後のソースを新しい版として採用")
    commands.add_parser("list", help="未整理URLとローカルソースの取得状態を表示")
    commands.add_parser("rebuild", help="Inbox.mdを原本から再生成")
    args = parser.parse_args()
    try:
        return run_command(args)
    except (InboxError, InvalidURL) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError):
        print("エラー: ローカルファイルまたはWorkspaceを処理できません。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
