import hashlib
import json
import os
import sys
import unittest
from unittest.mock import patch

import atc_source
import note
from test_note import CPP, InboxFixture, PROBLEM, PYTHON


class ResolveTests(InboxFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.cli("add", PROBLEM)

    def test_success_uses_exact_task_id_and_reuses_immutable_snapshot(self):
        self.fixture_result()
        registered = self.rows()[0]["registered_at"]
        self.resolve()
        self.assertEqual(self.calls(), [
            ["source", "example", "--task-id", "reused_task_a", "--workspace", str(self.workspace), "--json"],
        ])
        record, = self.rows()
        metadata = record["local_source"]
        digest = hashlib.sha256(CPP.encode()).hexdigest()
        self.assertEqual(metadata, {"origin": "atc-rs-local", "index": "A", "language": "cpp", "sha256": digest})
        self.assertEqual(record["registered_at"], registered)
        path, = self.snapshots.iterdir()
        self.assertEqual(path.read_bytes(), CPP.encode())
        self.assertEqual(path.name, digest + ".cpp")
        fingerprint = self.source.read_bytes(), path.stat().st_mtime_ns
        self.resolve()
        self.assertEqual((self.source.read_bytes(), path.stat().st_mtime_ns), fingerprint)
        rendered = self.cli("list").stdout
        self.assertIn("ローカルソース照合済み", rendered)
        self.assertIn(digest[:12], rendered)
        self.assertNotIn(str(self.workspace), rendered + self.source.read_text(encoding="utf-8"))
        self.assertNotIn("int main", rendered + self.view.read_text(encoding="utf-8"))

    def test_mismatched_task_identity_blocks_without_writing_code(self):
        self.fixture_result(task_id="some_other_task")
        self.resolve(code=1)
        self.assertEqual((self.rows()[0]["status"], self.rows()[0]["resolution_error"]),
                         ("blocked", "identity_mismatch"))
        self.assertFalse(self.snapshots.exists())

    def test_problem_url_for_same_task_but_different_contest_is_not_merged(self):
        another = PROBLEM.replace("/example/", "/reused/")
        self.cli("add", another)
        self.resolve(code=1)
        self.assertEqual({r["resolution_error"] for r in self.rows()}, {"task_conflict"})
        self.assertFalse(self.calls())

    def test_bad_url_path_and_language_are_detected(self):
        good = {
            "schema_version": 1, "contest_id": "example", "index": "A",
            "task_id": "reused_task_a", "url": PROBLEM, "language": "cpp",
            "source_path": str(self.workspace / "example" / "A.cpp"), "source": CPP,
        }
        for changes, selection in (
            ({"contest_id": "other"}, None),
            ({"url": PROBLEM.replace("atcoder.jp", "example.org")}, None),
            ({"source_path": str(self.root / "outside" / "example" / "A.cpp")}, None),
            ({"source_path": str(self.workspace / "example" / "B.cpp")}, None),
            ({}, "python"),
        ):
            with self.subTest(changes=changes, selection=selection):
                with self.assertRaises(atc_source.SourceError) as raised:
                    atc_source.parse_export(json.dumps({**good, **changes}).encode(), self.rows()[0],
                                            self.workspace, selection)
                self.assertEqual(raised.exception.code, "identity_mismatch")

    def test_multiple_languages_require_explicit_choice(self):
        self.fixture_error("multiple source files for problem A; select one with --language")
        result = self.resolve(code=1)
        self.assertIn("--language cpp", result.stdout)
        self.assertEqual(self.rows()[0]["resolution_error"], "language_required")
        self.assertEqual(self.rows()[0]["status"], "pending")
        self.fixture_result(language="python", source=PYTHON, source_path=str(self.workspace / "example" / "A.py"))
        self.resolve("--language", "python")
        self.assertEqual(self.calls()[-1][-2:], ["--language", "python"])
        self.assertEqual(self.rows()[0]["local_source"]["language"], "python")

    def test_expected_cli_errors_keep_record_pending_and_hide_paths(self):
        for message, code in (
            ("contest directory not found:", "contest_missing"),
            ("contest metadata not found:", "metadata_missing"),
            ("task ID not found in contest", "task_missing"),
            ("source file not found for problem A", "source_missing"),
            ("unrecognized subcommand 'source'", "atc_unsupported"),
            ("unknown atc error", "atc_failed"),
        ):
            with self.subTest(code=code):
                self.fixture_error(message)
                result = self.resolve(code=1)
                self.assertNotIn(str(self.workspace), result.stdout + result.stderr)
                self.assertEqual(self.rows()[0]["resolution_error"], code)
                self.assertEqual(self.rows()[0]["status"], "pending")
        self.assertFalse(self.snapshots.exists())

    def test_missing_workspace_and_atc(self):
        self.cli("resolve", "--workspace", str(self.root / "missing"), code=1)
        self.assertEqual(self.rows()[0]["resolution_error"], "workspace_missing")
        self.assertFalse(self.calls())
        self.atc.unlink()
        self.resolve(code=1)
        self.assertEqual(self.rows()[0]["resolution_error"], "atc_missing")

    def test_bad_json_and_schema_leave_snapshot_unwritten(self):
        for raw in ("{corrupt", '{"a":1,"a":2}', "{} {}"):
            self.fixture.write_text(json.dumps({"raw": raw}), encoding="utf-8")
            self.resolve(code=1)
            self.assertEqual(self.rows()[0]["resolution_error"], "invalid_json")
        for kwargs in ({"schema_version": 2}, {"schema_version": True}, {"language": "rust"}, {"source": 1}):
            self.fixture_result(**kwargs)
            self.resolve(code=1)
            self.assertEqual(self.rows()[0]["resolution_error"], "invalid_schema")
        for source in ("\0", "\ud800", "x" * (atc_source.MAX_SOURCE_BYTES + 1)):
            self.fixture_result(source=source)
            self.resolve(code=1)
            self.assertEqual(self.rows()[0]["resolution_error"], "invalid_source")
        self.assertFalse(self.snapshots.exists())

    def test_empty_source_is_a_valid_exact_snapshot(self):
        self.fixture_result(source="")
        self.resolve()
        path, = self.snapshots.iterdir()
        self.assertEqual(path.read_bytes(), b"")

    def test_timeout_is_retryable(self):
        self.fixture.write_text(json.dumps({"wait": 3}), encoding="utf-8")
        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(atc_source, "TIMEOUT_SECONDS", 0.15),
            self.assertRaises(atc_source.SourceError) as raised,
        ):
            atc_source.fetch_source(self.rows()[0], self.workspace, None)
        self.assertEqual(raised.exception.code, "timeout")
        self.assertEqual(self.rows()[0]["status"], "pending")

    def test_changed_source_requires_acceptance_and_keeps_both_snapshots(self):
        self.fixture_result()
        self.resolve()
        old = self.rows()[0]["local_source"]
        initial, = self.snapshots.iterdir()
        self.fixture_result(source="int main() { return 1; }\n")
        self.resolve(code=1)
        waiting, = self.rows()
        self.assertEqual(waiting["status"], "pending")
        self.assertEqual(waiting["resolution_error"], "source_changed")
        self.assertEqual(waiting["local_source"], old)
        self.assertEqual(list(self.snapshots.iterdir()), [initial])
        self.resolve("--accept-source-change")
        new = self.rows()[0]["local_source"]
        self.assertNotEqual(new["sha256"], old["sha256"])
        self.assertEqual(initial.read_bytes(), CPP.encode())
        self.assertEqual(len(list(self.snapshots.iterdir())), 2)

    def test_changed_problem_index_blocks_even_with_acceptance(self):
        self.fixture_result()
        self.resolve()
        original = self.rows()[0]["local_source"]
        self.fixture_result(index="B", source_path=str(self.workspace / "example" / "B.cpp"))
        self.resolve("--accept-source-change", code=1)
        self.assertEqual(self.rows()[0]["status"], "blocked")
        self.assertEqual(self.rows()[0]["local_source"], original)

    def test_existing_snapshot_with_wrong_content_is_never_overwritten(self):
        self.fixture_result()
        self.resolve()
        snapshot, = self.snapshots.iterdir()
        snapshot.write_text("unrelated", encoding="utf-8")
        self.resolve("--accept-source-change", code=1)
        self.assertEqual(self.rows()[0]["resolution_error"], "snapshot_conflict")
        self.assertEqual(snapshot.read_text(encoding="utf-8"), "unrelated")

    def test_save_failures_do_not_publish_dangling_records(self):
        self.fixture_result()
        previous = self.source.read_bytes()
        argv = ["note.py", "resolve", "--workspace", str(self.workspace)]
        real_write = note.atomic_write

        def failure(path, content, local, **options):
            if path == self.source:
                raise OSError("simulated commit failure")
            real_write(path, content, local, **options)

        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(note, "VAULT", self.root),
            patch.object(sys, "argv", argv),
            patch.object(note, "atomic_write", side_effect=failure),
            patch.object(sys, "stderr"),
        ):
            self.assertEqual(note.main(), 1)
        self.assertEqual(self.source.read_bytes(), previous)
        path, = self.snapshots.iterdir()
        self.assertEqual(path.read_bytes(), CPP.encode())
        self.resolve()
        self.assertEqual(self.rows()[0]["status"], "resolved")
        self.assertEqual(list(self.snapshots.iterdir()), [path])

    def test_snapshot_write_failure_retains_pending(self):
        self.fixture_result()
        argv = ["note.py", "resolve", "--workspace", str(self.workspace)]
        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(note, "VAULT", self.root),
            patch.object(sys, "argv", argv),
            patch.object(note.os, "link", side_effect=OSError("simulated storage failure")),
            patch.object(sys, "stdout"),
        ):
            self.assertEqual(note.main(), 1)
        self.assertEqual(self.rows()[0]["resolution_error"], "storage_error")
        self.assertEqual(self.rows()[0]["status"], "pending")
        self.assertNotIn("local_source", self.rows()[0])
        self.assertFalse(list(self.snapshots.iterdir()))
