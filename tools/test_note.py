from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import note


SUBMISSION = "https://atcoder.jp/contests/example/submissions/900000001"
OTHER_SUBMISSION = "https://atcoder.jp/contests/example/submissions/900000002"
PROBLEM = "https://atcoder.jp/contests/example/tasks/another_task_a"


class InboxTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        self.script = self.root / "tools" / "note.py"
        self.script.parent.mkdir()
        shutil.copyfile(note.__file__, self.script)
        shutil.copyfile(Path(note.__file__).with_name("atcoder.py"), self.script.with_name("atcoder.py"))
        self.source = self.root / ".local" / "inbox.jsonl"
        self.view = self.root / "Inbox.md"

    def cli(self, *args, success=True):
        result = subprocess.run(
            [sys.executable, self.script, *args],
            cwd=self.root / "tools",
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(result.stderr)
            self.assertEqual(result.stdout, "")
        return result

    def records(self):
        return [json.loads(line) for line in self.source.read_text(encoding="utf-8").splitlines()]

    def test_submission_and_problem_keep_only_known_identifiers(self):
        self.cli("add", SUBMISSION)
        self.cli("add", PROBLEM)
        submission, problem = self.records()
        self.assertEqual(
            {key: value for key, value in submission.items() if key != "registered_at"},
            {
                "schema_version": 1,
                "kind": "submission",
                "url": SUBMISSION,
                "contest_id": "example",
                "submission_id": "900000001",
                "task_id": None,
                "status": "pending",
            },
        )
        self.assertIsNotNone(datetime.fromisoformat(submission["registered_at"]).utcoffset())
        self.assertEqual(problem["kind"], "problem")
        self.assertEqual(problem["contest_id"], "example")
        self.assertEqual(problem["task_id"], "another_task_a")
        self.assertIsNone(problem["submission_id"])

        contents = self.view.read_text(encoding="utf-8")
        self.assertIn(f"[提出]({SUBMISSION}) | `example` | `900000001` | 未解決", contents)
        self.assertIn(f"[問題]({PROBLEM}) | `example` | — | `another_task_a`", contents)
        self.assertIn("未整理", contents)
        self.assertIn(submission["registered_at"], contents)
        self.assertIn(PROBLEM, self.cli("list").stdout)

    def test_duplicates_keep_original_bytes_and_distinct_submissions(self):
        self.cli("add", SUBMISSION)
        original = self.source.read_bytes()
        variants = [
            SUBMISSION,
            SUBMISSION + "/?unused=value#section",
            "  " + SUBMISSION.replace("atcoder.jp", "ATCODER.JP:443") + "  ",
        ]
        for url in variants:
            with self.subTest(url=url):
                self.assertIn("登録済み", self.cli("add", url).stdout)
                self.assertEqual(self.source.read_bytes(), original)
        self.cli("add", OTHER_SUBMISSION)
        self.assertEqual([record["url"] for record in self.records()], [SUBMISSION, OTHER_SUBMISSION])

    def test_invalid_urls_do_not_create_an_inbox(self):
        invalid = [
            "not-a-url",
            SUBMISSION.replace("https:", "http:"),
            SUBMISSION.replace("atcoder.jp", "atcoder.jp.example"),
            SUBMISSION.replace("atcoder.jp", "name@atcoder.jp"),
            SUBMISSION.replace("atcoder.jp", "atcoder.jp:8080"),
            SUBMISSION.replace("example", "ex\nample"),
            SUBMISSION.replace("900000001", "900a"),
            SUBMISSION + "/extra",
            PROBLEM + "//",
            PROBLEM.replace("another_task_a", "%2e%2e"),
        ]
        for url in invalid:
            with self.subTest(url=url):
                self.cli("add", url, success=False)
        self.assertFalse(self.source.parent.exists())
        self.assertFalse(self.view.exists())

    def test_empty_and_rebuild_from_source(self):
        self.assertIn("未整理のURLはありません", self.cli("list").stdout)
        self.assertFalse(self.view.exists())
        self.cli("rebuild")
        self.assertIn("未整理のURLはありません", self.view.read_text(encoding="utf-8"))
        self.cli("add", PROBLEM)
        source, view = self.source.read_bytes(), self.view.read_bytes()
        self.view.unlink()
        self.cli("rebuild")
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(self.view.read_bytes(), view)

    def test_concurrent_adds_and_rebuilds_preserve_all_urls(self):
        operations = [
            ("add", SUBMISSION),
            ("add", OTHER_SUBMISSION),
            ("rebuild",),
            ("add", PROBLEM),
            ("add", SUBMISSION + "/"),
        ]
        with ThreadPoolExecutor() as executor:
            list(executor.map(lambda args: self.cli(*args), operations))
        self.assertCountEqual(
            [record["url"] for record in self.records()],
            [SUBMISSION, OTHER_SUBMISSION, PROBLEM],
        )
        self.assertIn(self.cli("list").stdout, self.view.read_text(encoding="utf-8"))

    def test_failed_view_write_keeps_source_for_retry(self):
        self.view.mkdir()
        result = self.cli("add", SUBMISSION, success=False)
        self.assertIn("Inbox.mdを更新できません", result.stderr)
        self.assertEqual([record["url"] for record in self.records()], [SUBMISSION])
        self.view.rmdir()
        self.assertIn("登録済み", self.cli("add", SUBMISSION).stdout)
        self.assertIn(SUBMISSION, self.view.read_text(encoding="utf-8"))
        self.assertEqual(len(self.records()), 1)

    def test_failed_source_replace_leaves_previous_files_intact(self):
        self.cli("add", SUBMISSION)
        source, view = self.source.read_bytes(), self.view.read_bytes()
        args = ["note.py", "add", OTHER_SUBMISSION]
        with (
            patch.object(note, "VAULT", self.root),
            patch.object(sys, "argv", args),
            patch.object(note.os, "replace", side_effect=OSError("simulated replace failure")),
            patch.object(sys, "stdout") as stdout,
            patch.object(sys, "stderr") as stderr,
        ):
            self.assertEqual(note.main(), 1)
            stdout.write.assert_not_called()
            self.assertIn("simulated replace failure", stderr.write.call_args_list[0].args[0])
        self.assertEqual(self.source.read_bytes(), source)
        self.assertEqual(self.view.read_bytes(), view)
        self.assertCountEqual([path.name for path in self.source.parent.iterdir()], ["inbox.jsonl", "inbox.lock"])

    def test_corrupt_or_unsupported_source_is_never_overwritten(self):
        self.cli("add", SUBMISSION)
        source, view = self.source.read_bytes(), self.view.read_bytes()
        corrupt_rows = [b"{\n", b"\xff\n", b'{"schema_version":2}\n']
        for row in corrupt_rows:
            with self.subTest(row=row):
                self.source.write_bytes(source + row)
                for args in [("add", OTHER_SUBMISSION), ("rebuild",)]:
                    self.assertIn("2行目", self.cli(*args, success=False).stderr)
                    self.assertEqual(self.source.read_bytes(), source + row)
                    self.assertEqual(self.view.read_bytes(), view)

    def test_phase_one_records_can_be_read_and_upgraded(self):
        self.source.parent.mkdir()
        timestamp = "2026-11-19T12:00:00+09:00"
        record = {"kind": "submission", "url": SUBMISSION, "registered_at": timestamp}
        self.source.write_text(json.dumps(record) + "\n", encoding="utf-8")
        previous = self.source.read_bytes()
        self.cli("rebuild")
        self.assertIn("未解決", self.view.read_text(encoding="utf-8"))
        self.assertEqual(self.source.read_bytes(), previous)
        self.cli("add", PROBLEM)
        migrated = self.records()[0]
        self.assertEqual(migrated["registered_at"], timestamp)
        self.assertEqual(migrated["url"], SUBMISSION)
        self.assertEqual(migrated["schema_version"], 1)

    def test_organized_rows_stay_in_source_and_are_hidden_from_pending_list(self):
        self.cli("add", SUBMISSION)
        record = {**self.records()[0], "task_id": "another_task_a", "status": "organized"}
        self.source.write_text(json.dumps(record) + "\n", encoding="utf-8")
        original = self.source.read_bytes()
        self.cli("rebuild")
        self.assertIn("未整理のURLはありません", self.view.read_text(encoding="utf-8"))
        self.assertIn("登録済み", self.cli("add", SUBMISSION).stdout)
        self.assertEqual(self.source.read_bytes(), original)

    def test_unrelated_notes_and_code_are_unchanged(self):
        protected = {"ノート.md": b"# note\n", "template.cpp": b"// code\n"}
        for name, data in protected.items():
            (self.root / name).write_bytes(data)
        self.cli("add", SUBMISSION)
        self.cli("list")
        self.cli("rebuild")
        for name, data in protected.items():
            self.assertEqual((self.root / name).read_bytes(), data)
