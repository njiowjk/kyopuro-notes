"""Read and verify local problem sources exported by atc-rs."""

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess

from atcoder import InvalidURL, parse_url


EXPORT_VERSION = 1
MAX_SOURCE_BYTES = 1024 * 1024
# JSON may use six bytes to encode one byte of source.
MAX_EXPORT_BYTES = 7 * MAX_SOURCE_BYTES
TIMEOUT_SECONDS = 10
EXTENSIONS = {"cpp": "cpp", "python": "py"}
TEXT_FIELDS = ("contest_id", "task_id", "index", "url", "language", "source_path", "source")
ERROR_LABELS = {
    "atc_missing": "atc-rsが見つからない",
    "atc_unsupported": "atc source対応版が必要",
    "atc_failed": "atc sourceの実行に失敗",
    "workspace_missing": "Workspaceディレクトリが見つからない",
    "contest_missing": "Workspaceにコンテストが見つからない",
    "metadata_missing": "コンテストのメタデータが見つからない",
    "metadata_unavailable": "コンテストのメタデータを安全に読み取れない",
    "task_missing": "コンテストのメタデータにtask IDが見つからない",
    "source_missing": "ローカルソースが見つからない",
    "language_required": "`--language cpp` または `--language python` で言語を選んでください",
    "timeout": "atc sourceがタイムアウト",
    "invalid_json": "atc sourceの出力が単一のUTF-8 JSONではない",
    "invalid_schema": "atc sourceのJSON形式またはバージョンが未対応",
    "identity_mismatch": "問題URL・識別子・言語と取得データの対応に矛盾",
    "invalid_source": "ソースが有効なUTF-8テキストではないかサイズ上限を超過",
}


class SourceError(Exception):
    def __init__(self, code):
        super().__init__(ERROR_LABELS[code])
        self.code = code


@dataclass(frozen=True)
class SourceExport:
    index: str
    language: str
    content: bytes = field(repr=False)


def is_problem_index(value):
    return (
        isinstance(value, str)
        and not value.endswith((" ", "."))
        and re.fullmatch(r'[^/\\\x00-\x1f<>:"|?*]+', value) is not None
    )


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_export(raw, record, workspace, language):
    if len(raw) > MAX_EXPORT_BYTES:
        raise SourceError("invalid_schema")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (ValueError, RecursionError):
        raise SourceError("invalid_json") from None
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", *TEXT_FIELDS}
        or type(data["schema_version"]) is not int
        or data["schema_version"] != EXPORT_VERSION
        or not all(isinstance(data[key], str) for key in TEXT_FIELDS)
        or data["language"] not in EXTENSIONS
        or not is_problem_index(data["index"])
    ):
        raise SourceError("invalid_schema")

    try:
        problem = parse_url(data["url"])
    except InvalidURL:
        raise SourceError("identity_mismatch") from None
    try:
        data["index"].encode("utf-8")
        data["source_path"].encode("utf-8")
    except UnicodeEncodeError:
        raise SourceError("invalid_schema") from None
    path = Path(data["source_path"])
    extension = EXTENSIONS[data["language"]]
    if (
        problem["kind"] != "problem"
        or problem["url"] != record["url"]
        or data["contest_id"] != record["contest_id"]
        or data["task_id"] != record["task_id"]
        or (language is not None and data["language"] != language)
        or not path.is_absolute()
        or not path.is_relative_to(workspace)
        or (".." in path.parts or "\0" in data["source_path"])
        or path.parent.name != data["contest_id"]
        or path.name != f"{data['index']}.{extension}"
    ):
        raise SourceError("identity_mismatch")
    try:
        content = data["source"].encode("utf-8")
    except UnicodeEncodeError:
        raise SourceError("invalid_source") from None
    if len(content) > MAX_SOURCE_BYTES or b"\0" in content:
        raise SourceError("invalid_source")
    return SourceExport(data["index"], data["language"], content)


def classify_failure(stderr):
    # atc source currently returns a human-readable stderr rather than error JSON.
    # Keep its output private because diagnostics can include absolute paths.
    message = stderr[:32768].decode("utf-8", errors="replace").lower()
    for fragment, code in (
        ("unrecognized subcommand 'source'", "atc_unsupported"),
        ("select one with --language", "language_required"),
        ("contest id mismatch", "identity_mismatch"),
        ("unsafe problem url", "identity_mismatch"),
        ("duplicate task id", "identity_mismatch"),
        ("duplicate problem index", "identity_mismatch"),
        ("contest directory not found", "contest_missing"),
        ("workspace marker not found", "metadata_missing"),
        ("contest metadata not found", "metadata_missing"),
        ("requires recovery check", "metadata_unavailable"),
        ("validate contest metadata", "metadata_unavailable"),
        ("source file not found", "source_missing"),
        ("not found in contest", "task_missing"),
        ("not valid utf-8", "invalid_source"),
        ("exceeds 1048576 bytes", "invalid_source"),
    ):
        if fragment in message:
            return code
    return "atc_failed"


def fetch_source(record, workspace, language):
    if not workspace.is_dir():
        raise SourceError("workspace_missing")
    command = [
        "atc", "source", record["contest_id"], "--task-id", record["task_id"],
        "--workspace", str(workspace), "--json",
    ]
    if language is not None:
        command.extend(["--language", language])
    try:
        result = subprocess.run(command, capture_output=True, timeout=TIMEOUT_SECONDS, check=False)
    except FileNotFoundError:
        raise SourceError("atc_missing") from None
    except subprocess.TimeoutExpired:
        raise SourceError("timeout") from None
    except OSError:
        raise SourceError("atc_failed") from None
    if result.returncode:
        raise SourceError(classify_failure(result.stderr))
    return parse_export(result.stdout, record, workspace, language)
