"""Register and group AtCoder URLs in the local Obsidian inbox."""

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from atc_cookie import load_session_cookie
from atcoder import ATCODER_ID, InvalidURL, ResolutionError, fetch_task, parse_url

if os.name == "nt":
    import msvcrt
else:
    import fcntl


VAULT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
REQUEST_INTERVAL_SECONDS = 1
STATUS_LABELS = {
    "pending": "未整理（未解決）",
    "resolved": "解決済み・未整理",
    "organized": "整理済み",
    "blocked": "保留",
}
ERROR_LABELS = {
    "timeout": "タイムアウト",
    "network": "通信エラー",
    "unexpected_page": "提出ページを確認できない",
    "unsafe_redirect": "許可されていないリダイレクトまたは応答URL",
    "html_too_large": "HTMLのサイズ上限超過",
    "missing_task_link": "問題リンクを確認できない",
    "ambiguous_task_link": "問題リンクが複数ある",
    "task_conflict": "同じtask IDに異なる問題URL",
    "submission_conflict": "同じ提出IDに異なる提出URLまたは問題URL",
    "task_id_mismatch": "既存のtask IDとページ上のtask IDが不一致",
}
COOKIE_WARNINGS = {
    "permissions": "ファイルまたは保存先の権限を確認できません。",
    "path": "保存先が安全な通常のファイルを指していません。",
    "format": "保存形式が正しくありません。",
    "read": "ファイルを読み取れません。",
}


class InboxError(Exception):
    """An input or inbox error that can be shown without a traceback."""


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
        raise InboxError("解決済みの提出には確認済みの問題URLが必要です。")
    if record.get("resolution_error") is not None and not isinstance(record["resolution_error"], str):
        raise InboxError("解決エラーの形式が正しくありません。")
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
                reason = str(error) if isinstance(error, (InboxError, InvalidURL)) else "JSONまたはUTF-8が不正です。"
                raise InboxError(f".local/inbox.jsonl の{number}行目: {reason}") from error
    return records


def problem_url(record):
    return record["url"] if record["kind"] == "problem" else record.get("problem_url")


def submission_number(record):
    return record["submission_id"].lstrip("0") or "0"


def conflicts(records):
    by_task = defaultdict(list)
    by_submission = defaultdict(list)
    for record in records:
        if problem_url(record):
            by_task[record["task_id"]].append(record)
        if record["kind"] == "submission":
            by_submission[submission_number(record)].append(record)

    issues = {}
    for entries in by_task.values():
        if len({problem_url(entry) for entry in entries}) > 1:
            issues.update((entry["url"], "task_conflict") for entry in entries)
    for entries in by_submission.values():
        urls = {entry["url"] for entry in entries}
        targets = {target for entry in entries if (target := problem_url(entry))}
        if len(urls) > 1 or len(targets) > 1:
            issues.update((url, "submission_conflict") for url in urls)
    return issues


def group_inbox(records):
    """Return unorganized problem groups and individual entries needing attention."""
    issues = conflicts(records)
    groups = {}
    remaining = []
    seen = set()
    for record in records:
        if record["status"] == "organized" or record["url"] in seen:
            continue
        seen.add(record["url"])
        issue = issues.get(record["url"])
        target = problem_url(record)
        if issue:
            remaining.append({**record, "status": "blocked", "resolution_error": issue})
        elif target and (
            record["status"] == "resolved"
            or (record["kind"] == "problem" and record["status"] == "pending")
        ):
            group = groups.setdefault(
                record["task_id"],
                {
                    "task_id": record["task_id"],
                    "problem_url": target,
                    "representative_submission_url": None,
                    "entries": [],
                },
            )
            group["entries"].append(record)
        else:
            remaining.append(record)
    return list(groups.values()), remaining


def error_label(code):
    if code is None:
        return ""
    if re.fullmatch(r"http_[0-9]{3}", code):
        return f"HTTP {code.removeprefix('http_')}"
    return ERROR_LABELS.get(code, "解決エラー")


def format_entry(record, status=None):
    submission_id = record["submission_id"]
    task_id = record["task_id"]
    label = "提出" if submission_id is not None else "問題"
    submission = f"`{submission_id}`" if submission_id is not None else "—"
    task = f"`{task_id}`" if task_id is not None else "未解決"
    timestamp = datetime.fromisoformat(record["registered_at"]).isoformat()
    state = STATUS_LABELS[status or record["status"]]
    reason = error_label(record.get("resolution_error"))
    if reason:
        state += f"（{reason}）"
    return (
        f"| [{label}]({record['url']}) | `{record['contest_id']}` | "
        f"{submission} | {task} | {timestamp} | {state} |"
    )


def inbox_table(rows):
    return [
        "| AtCoder | コンテストID | 提出ID | task ID | 登録日時 | 整理状態 |",
        "| --- | --- | --- | --- | --- | --- |",
        *rows,
        "",
    ]


def submission_order(record):
    if record["kind"] == "problem":
        return (0, "")
    number = submission_number(record)
    return (len(number), number)


def render_inbox(records):
    groups, remaining = group_inbox(records)
    if not groups and not remaining:
        return "# Inbox\n\n未整理のURLはありません。\n"
    lines = ["# Inbox", ""]
    if groups:
        lines.extend(["## 解決済みの問題", ""])
        for group in groups:
            lines.extend([
                f"### [{group['task_id']}]({group['problem_url']})",
                "",
                "代表提出 未選定",
                "",
                *inbox_table(
                    format_entry(entry, "resolved")
                    for entry in sorted(group["entries"], key=submission_order)
                ),
            ])
    if remaining:
        lines.extend(["## 未解決・保留", "", *inbox_table(map(format_entry, remaining))])
    return "\n".join(lines)


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


def write_records(source, records):
    atomic_write(source, "".join(json.dumps(record) + "\n" for record in records), source.parent)


def write_view(local, records, *, saved):
    view = "<!-- 生成元 .local/inbox.jsonl。再生成は python3 tools/note.py rebuild -->\n\n"
    try:
        atomic_write(VAULT / "Inbox.md", view + render_inbox(records), local)
    except OSError as error:
        details = "原本には変更が保存されています。" if saved else ""
        raise InboxError(
            f"Inbox.mdを更新できません。{details} 原因を解消して rebuild を実行してください。"
            f"（{error.strerror or error}）"
        ) from error


def fetch_pending(records):
    issues = conflicts(records)
    outcomes = {}
    session = None
    for record in records:
        url = record["url"]
        if (
            record["status"] != "pending"
            or record["kind"] != "submission"
            or url in outcomes
            or url in issues
        ):
            continue
        if outcomes:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        if session is None:
            session = load_session_cookie()
            if notice := COOKIE_WARNINGS.get(session.state):
                print(f"atc-rsの認証情報を使用せず取得します。{notice}", file=sys.stderr)
        try:
            if session.header is None:
                outcomes[url] = fetch_task(url)
            else:
                outcomes[url] = fetch_task(url, session=session)
        except ResolutionError as error:
            outcomes[url] = error
            if error.code == "http_429":
                break
    return outcomes, session.state if session is not None else None


def apply_resolutions(records, outcomes):
    updated = []
    for record in records:
        if record["status"] != "pending":
            updated.append(record)
            continue

        outcome = outcomes.get(record["url"])
        if record["kind"] == "problem":
            outcome = {"task_id": record["task_id"], "url": record["url"]}
        if isinstance(outcome, ResolutionError):
            status = "blocked" if outcome.blocked else "pending"
            record = {**record, "status": status, "resolution_error": outcome.code}
        elif outcome is not None:
            if record["task_id"] not in (None, outcome["task_id"]):
                record = {**record, "status": "blocked", "resolution_error": "task_id_mismatch"}
            else:
                record = {
                    **record,
                    "status": "resolved",
                    "task_id": outcome["task_id"],
                    "problem_url": outcome["url"],
                }
                record.pop("resolution_error", None)
        updated.append(record)

    issues = conflicts(updated)
    for index, (previous, record) in enumerate(zip(records, updated)):
        if previous["status"] == "pending" and (issue := issues.get(record["url"])):
            updated[index] = {**record, "status": "blocked", "resolution_error": issue}
    return updated


def run_resolve(source):
    local = source.parent
    with file_lock(local / "resolve.lock"):
        # Allow offline registration while network requests are in progress.
        outcomes, session_state = fetch_pending(read_records(source))
        with file_lock(local / "inbox.lock"):
            records = read_records(source)
            updated = apply_resolutions(records, outcomes)
            changed = updated != records
            if changed:
                write_records(source, updated)
            write_view(local, updated, saved=changed)

    transitions = Counter(
        new["status"]
        for old, new in zip(records, updated)
        if old["status"] == "pending" and new["status"] != "pending"
    )
    retryable = Counter(
        error_label(entry.get("resolution_error"))
        for entry in updated
        if entry["status"] == "pending" and entry["url"] in outcomes
    )
    for reason, count in sorted(retryable.items()):
        print(f"再試行待ち {count}件（{reason}）")
    failure_codes = {result.code for result in outcomes.values() if isinstance(result, ResolutionError)}
    if "http_403" in failure_codes:
        if session_state == "loaded":
            context = "atc-rsの保存済み認証情報を送信しました。"
        elif session_state == "missing":
            context = "atc-rsの保存済み認証情報が見つからず、未認証で取得しました。"
        else:
            context = "atc-rsの保存済み認証情報を読み込めず、未認証で取得しました。"
        print(f"HTTP 403。{context} 403の原因やセッションの有効性は確認できません。")
    if "http_429" in failure_codes:
        print("HTTP 429のため後続の取得を中止しました。時間をおいて再実行してください。")
    print(
        f"今回の解決 {transitions['resolved']}件、保留 {transitions['blocked']}件。"
        f"未解決 {sum(entry['status'] == 'pending' for entry in updated)}件。"
    )


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
    if args.command == "resolve":
        run_resolve(source)
        return
    with file_lock(local / "inbox.lock"):
        records = read_records(source)
        added = fields is not None and all(record["url"] != fields["url"] for record in records)
        if added:
            record = {
                "schema_version": SCHEMA_VERSION,
                **fields,
                "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": "resolved" if fields["kind"] == "problem" else "pending",
            }
            records.append(record)
            if (issue := conflicts(records).get(record["url"])) and record["kind"] == "problem":
                record.update(status="blocked", resolution_error=issue)
            write_records(source, records)
        write_view(local, records, saved=added)

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
    commands.add_parser("resolve", help="未解決の提出ページから問題リンクを取得")
    commands.add_parser("list", help="未整理URLの一覧を表示")
    commands.add_parser("rebuild", help="Inbox.mdを原本から再生成")
    args = parser.parse_args()
    try:
        run_command(args)
    except (InboxError, InvalidURL, OSError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
