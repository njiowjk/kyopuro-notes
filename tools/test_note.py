from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import note


PROBLEM = "https://atcoder.jp/contests/example/tasks/reused_task_a"
SECOND = "https://atcoder.jp/contests/example/tasks/reused_task_b"
SUBMISSION = "https://atcoder.jp/contests/example/submissions/900000001"
CPP = "int main() { return 0; }\r\n"
PYTHON = "print('example')\n"
ENTERED = "2026-11-19T12:00:00+09:00"

FAKE_ATC = """import json
import os
from pathlib import Path
import sys
import time

config = Path(os.environ['NOTE_ATC_FIXTURE'])
with config.with_suffix('.calls').open('a') as file:
    file.write(json.dumps(sys.argv[1:]) + '\\n')
fixture = json.loads(config.read_bytes())
if fixture.get('wait'):
    time.sleep(fixture['wait'])
sys.stderr.write(fixture.get('stderr', ''))
if 'raw' in fixture:
    sys.stdout.write(fixture['raw'])
elif 'result' in fixture:
    print(json.dumps(fixture['result']))
sys.exit(fixture.get('exit', 0))
"""


class InboxFixture:
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name).resolve()
        self.tools = self.root / "tools"
        self.tools.mkdir()
        source = Path(note.__file__).parent
        for filename in ("note.py", "atcoder.py", "atc_source.py"):
            shutil.copyfile(source / filename, self.tools / filename)
        self.workspace = self.root / "Workspace root"
        self.workspace.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.atc = self.bin / "atc"
        self.fixture = self.root / "atc.json"
        self.fixture.write_text("{}", encoding="utf-8")
        if os.name == "nt":
            dummy = self.bin / "fake_atc.py"
            dummy.write_text(FAKE_ATC, encoding="utf-8")
            self.atc = self.bin / "atc.cmd"
            self.atc.write_text(f'@"{sys.executable}" "{dummy}" %*\n', encoding="utf-8")
        else:
            self.atc.write_text(f"#!{sys.executable}\n{FAKE_ATC}", encoding="utf-8")
            self.atc.chmod(0o700)
        self.env = {
            **os.environ, "PATH": str(self.bin), "NOTE_ATC_FIXTURE": str(self.fixture), "PYTHONUTF8": "1",
        }
        self.source = self.root / ".local" / "inbox.jsonl"
        self.config = self.source.with_name("config.toml")
        self.view = self.root / "Inbox.md"
        self.snapshots = self.root / ".local" / "sources"

    def cli(self, *args, code=0, cwd=None):
        result = subprocess.run(
            [sys.executable, "-B", self.tools / "note.py", *args],
            cwd=self.root if cwd is None else cwd,
            env=self.env,
            capture_output=True,
            encoding="utf-8",
            timeout=15,
        )
        self.assertEqual(result.returncode, code, result.stderr + result.stdout)
        return result

    def calls(self):
        log = self.fixture.with_suffix(".calls")
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def rows(self):
        return note.read_records(self.source)

    def fixture_result(self, **changes):
        result = {
            "schema_version": 1, "contest_id": "example", "index": "A",
            "task_id": "reused_task_a", "url": PROBLEM, "language": "cpp",
            "source_path": str(self.workspace / "mapped" / "example" / "A.cpp"),
            "source": CPP,
        }
        result.update(changes)
        self.fixture.write_text(json.dumps({"result": result}), encoding="utf-8")

    def fixture_error(self, message):
        error = "Error: filesystem operation failed: " + message + f" {self.workspace}/private"
        self.fixture.write_text(json.dumps({"stderr": error, "exit": 1}), encoding="utf-8")

    def resolve(self, *args, code=0):
        return self.cli("resolve", "--workspace", str(self.workspace), *args, code=code)


class InboxTests(InboxFixture, unittest.TestCase):
    def test_add_accepts_only_problems_and_stays_offline(self):
        for invalid in (SUBMISSION, "http:" + PROBLEM[6:], PROBLEM.replace("atcoder.jp", "example.org")):
            self.cli("add", invalid, code=1)
            self.assertFalse(self.source.exists())
        self.atc.unlink()
        self.cli("add", PROBLEM + "/?lang=ja#section")
        row, = self.rows()
        self.assertEqual((row["kind"], row["url"], row["task_id"], row["status"]),
                         ("problem", PROBLEM, "reused_task_a", "pending"))
        self.assertIsNone(row["submission_id"])
        before = self.source.read_bytes()
        self.cli("add", PROBLEM.replace("atcoder.jp", "ATCODER.JP:443"))
        self.assertEqual(self.source.read_bytes(), before)
        self.assertIn(PROBLEM, self.cli("list").stdout)
        self.assertFalse(self.calls())
        self.assertFalse(self.config.exists())

    def test_legacy_submissions_are_kept_byte_for_byte(self):
        legacy = (
            b' { "kind": "submission", "url": "' + SUBMISSION.encode() +
            b'", "registered_at": "' + ENTERED.encode() + b'" }\r\n'
        )
        old = {
            **note.parse_url(SUBMISSION + "2"),
            "schema_version": 1, "registered_at": ENTERED, "status": "resolved",
            "task_id": "reused_task_a", "problem_url": PROBLEM,
        }
        original = legacy + b"\n" + json.dumps(old).encode() + b"\n"
        self.source.parent.mkdir()
        self.source.write_bytes(original)
        self.assertIn("旧方式の提出URL", self.cli("list").stdout)
        self.resolve()
        self.assertFalse(self.calls())
        self.cli("add", PROBLEM)
        self.fixture_result()
        self.resolve()
        self.assertTrue(self.source.read_bytes().startswith(original))
        self.assertEqual(self.rows()[0]["registered_at"], ENTERED)
        self.assertEqual(self.rows()[1], old)
        self.assertEqual(self.rows()[2]["status"], "resolved")

    def test_legacy_problem_with_resolved_status_requires_local_source(self):
        original = {
            **note.parse_url(PROBLEM), "schema_version": 1,
            "registered_at": ENTERED, "status": "resolved", "problem_url": PROBLEM,
        }
        self.source.parent.mkdir()
        self.source.write_text(json.dumps(original) + "\n", encoding="utf-8")
        self.assertIn("取得待ち", self.cli("list").stdout)
        self.fixture_result()
        self.resolve()
        self.assertEqual(self.rows()[0]["registered_at"], ENTERED)
        self.assertIn("local_source", self.rows()[0])

    def test_concurrent_registration_and_rebuild_retains_records_and_view(self):
        commands = [("add", PROBLEM), ("add", SECOND), ("rebuild",), ("add", PROBLEM + "/")]
        with ThreadPoolExecutor() as pool:
            list(pool.map(lambda args: self.cli(*args), commands))
        self.assertCountEqual([r["url"] for r in self.rows()], [PROBLEM, SECOND])
        self.assertIn(self.cli("list").stdout, self.view.read_text(encoding="utf-8"))
        self.assertFalse(self.calls())

    def test_empty_rebuild_and_malformed_inbox(self):
        self.assertIn("未整理のURLはありません", self.cli("list").stdout)
        self.cli("rebuild")
        self.assertIn("未整理のURLはありません", self.view.read_text(encoding="utf-8"))
        broken = b'{"schema_version":2}\n'
        self.source.write_bytes(broken)
        self.cli("add", PROBLEM, code=1)
        self.resolve(code=1)
        self.assertEqual(self.source.read_bytes(), broken)
        self.assertFalse(self.calls())
