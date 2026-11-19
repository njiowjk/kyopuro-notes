from email.message import Message
from http.client import IncompleteRead
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request

import atcoder
import note


BASE = "https://atcoder.jp/contests/example"
SUBMISSION = BASE + "/submissions/900000001"
SECOND = BASE + "/submissions/900000002"
THIRD = BASE + "/submissions/900000003"
PROBLEM = BASE + "/tasks/reused_task_a"
OTHER_PROBLEM = BASE + "/tasks/different_b"
HTML = (Path(__file__).parent / "fixtures" / "submission.html").read_text(encoding="utf-8")


def response(html=HTML, *, url=SUBMISSION, content_type="text/html"):
    reply = Mock()
    reply.__enter__ = Mock(return_value=reply)
    reply.__exit__ = Mock(return_value=False)
    reply.status = 200
    reply.headers = Message()
    reply.headers["Content-Type"] = content_type
    reply.geturl.return_value = url
    reply.read.return_value = html.encode()
    return reply


class AtCoderTests(unittest.TestCase):
    def test_valid_submission_returns_linked_task_and_skips_other_links(self):
        opener = Mock()
        opener.open.return_value = response(url=SUBMISSION + "?lang=ja")
        with patch.object(atcoder, "build_opener", return_value=opener):
            task = atcoder.fetch_task(SUBMISSION)
        self.assertEqual(task["url"], PROBLEM)
        self.assertEqual(task["task_id"], "reused_task_a")
        self.assertEqual(task["contest_id"], "example")
        request, = opener.open.call_args.args
        self.assertEqual(request.full_url, SUBMISSION)
        self.assertIsNone(request.get_header("Cookie"))
        self.assertIsNone(request.get_header("Authorization"))
        self.assertGreater(opener.open.call_args.kwargs["timeout"], 0)

    def test_http_and_transport_failures_use_fixed_codes(self):
        failures = [
            (HTTPError(SUBMISSION, code, "private detail", {}, BytesIO()), f"http_{code}")
            for code in (403, 404, 429)
        ]
        failures += [
            (TimeoutError("private detail"), "timeout"),
            (URLError(TimeoutError("private detail")), "timeout"),
            (IncompleteRead(b""), "network"),
        ]
        for failure, expected in failures:
            with self.subTest(expected=expected):
                opener = Mock()
                opener.open.side_effect = failure
                with patch.object(atcoder, "build_opener", return_value=opener):
                    with self.assertRaises(atcoder.ResolutionError) as raised:
                        atcoder.fetch_task(SUBMISSION)
                self.assertEqual(str(raised.exception), expected)
                self.assertFalse(raised.exception.blocked)

    def test_missing_external_or_ambiguous_task_links(self):
        bad_urls = [
            "https://outside.example/contests/example/tasks/reused_task_a",
            "https://name@atcoder.jp/contests/example/tasks/reused_task_a",
            "http://atcoder.jp/contests/example/tasks/reused_task_a",
        ]
        for url in bad_urls:
            html = HTML.replace("../tasks/reused_task_a?lang=ja", url)
            with self.subTest(url=url), self.assertRaisesRegex(atcoder.ResolutionError, "missing_task_link"):
                atcoder.extract_task(html, SUBMISSION)
        html = HTML.replace(
            '<a href="/users/example">', '<a href="/contests/example/tasks/different_b">'
        )
        with self.assertRaisesRegex(atcoder.ResolutionError, "ambiguous_task_link") as raised:
            atcoder.extract_task(html, SUBMISSION)
        self.assertTrue(raised.exception.blocked)

    def test_duplicate_task_links_and_other_contest_links(self):
        target = "https://atcoder.jp/contests/original/tasks/reused_task_a"
        html = HTML.replace("../tasks/reused_task_a?lang=ja", target)
        html = html.replace("/users/example", target + "/?lang=en#top")
        self.assertEqual(atcoder.extract_task(html, SUBMISSION)["url"], target)

    def test_redirects_are_validated_before_the_opener_follows_them(self):
        handler = atcoder.SubmissionRedirectHandler()
        request = Request(SUBMISSION)
        cases = [
            ("//outside.example/contests/example/submissions/900000001", "unsafe_redirect"),
            ("ftp://atcoder.jp/contests/example/submissions/900000001", "unsafe_redirect"),
            ("/login", "unexpected_page"),
            (SECOND, "unexpected_page"),
        ]
        with patch.object(HTTPRedirectHandler, "http_error_302") as follow:
            for target, reason in cases:
                with self.subTest(target=target), self.assertRaisesRegex(atcoder.ResolutionError, reason):
                    handler.http_error_302(request, BytesIO(), 302, "", {"location": target})
            follow.assert_not_called()
            handler.http_error_302(request, BytesIO(), 302, "", {"location": SUBMISSION + "?lang=en"})
            follow.assert_called_once()

    def test_response_url_and_content_type_are_verified(self):
        for url, content_type, reason in [
            ("https://outside.example/", "text/html", "unsafe_redirect"),
            (SECOND, "text/html", "unexpected_page"),
            (SUBMISSION, "application/json", "unexpected_page"),
        ]:
            opener = Mock()
            opener.open.return_value = response(url=url, content_type=content_type)
            with self.subTest(url=url), patch.object(atcoder, "build_opener", return_value=opener):
                with self.assertRaisesRegex(atcoder.ResolutionError, reason):
                    atcoder.fetch_task(SUBMISSION)
                opener.open.return_value.read.assert_not_called()


class ResolveInboxTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        self.source = self.root / ".local" / "inbox.jsonl"
        self.view = self.root / "Inbox.md"
        self.enterContext(patch.object(note, "VAULT", self.root))
        self.sleep = self.enterContext(patch.object(note.time, "sleep"))
        self.fetch = self.enterContext(patch.object(note, "fetch_task"))
        self.fetch.side_effect = AssertionError("unexpected network request")

    def cli(self, *args, expected=0):
        with (
            patch.object(sys, "argv", ["note.py", *args]),
            patch.object(sys, "stdout", new_callable=StringIO) as out,
            patch.object(sys, "stderr", new_callable=StringIO) as err,
        ):
            self.assertEqual(note.main(), expected, err.getvalue())
        return out.getvalue(), err.getvalue()

    def records(self):
        return note.read_records(self.source)

    def test_problem_url_resolves_without_network_and_legacy_rows_remain_readable(self):
        self.cli("add", PROBLEM)
        self.assertEqual(self.records()[0]["status"], "resolved")
        record = {**self.records()[0], "status": "pending"}
        self.source.write_text(json.dumps(record) + "\n", encoding="utf-8")
        self.cli("resolve")
        self.assertEqual(self.records()[0]["status"], "resolved")
        self.assertEqual(self.records()[0]["problem_url"], PROBLEM)
        self.fetch.assert_not_called()

    def test_groups_submissions_and_problem_record_without_losing_order_or_dates(self):
        for url in (SECOND, SUBMISSION, PROBLEM, THIRD):
            self.cli("add", url)
        original = [(row["url"], row["registered_at"]) for row in self.records()]
        self.fetch.side_effect = [
            note.parse_url(PROBLEM),
            note.parse_url(PROBLEM),
            note.parse_url(OTHER_PROBLEM),
        ]
        self.cli("resolve")
        records = self.records()
        self.assertEqual([(row["url"], row["registered_at"]) for row in records], original)
        groups, remaining = note.group_inbox(records)
        self.assertEqual([group["task_id"] for group in groups], ["reused_task_a", "different_b"])
        self.assertEqual([r["url"] for r in groups[0]["entries"]], [SECOND, SUBMISSION, PROBLEM])
        self.assertIsNone(groups[0]["representative_submission_url"])
        self.assertFalse(remaining)
        self.assertFalse(any("verdict" in row for row in records))
        markdown = self.view.read_text(encoding="utf-8")
        self.assertEqual(markdown.count(f"### [reused_task_a]({PROBLEM})"), 1)
        self.assertLess(markdown.index(SUBMISSION), markdown.index(SECOND))
        self.assertEqual(self.sleep.call_count, 2)
        before = self.source.read_bytes()
        self.cli("resolve")
        self.cli("rebuild")
        self.assertEqual(self.fetch.call_count, 3)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertIn(markdown.split("\n\n", 1)[1], self.cli("list")[0])

    def test_retryable_errors_keep_partial_success_and_stop_after_429(self):
        fourth = BASE + "/submissions/900000004"
        for url in (SUBMISSION, SECOND, THIRD, fourth):
            self.cli("add", url)
        self.fetch.side_effect = [
            note.parse_url(PROBLEM),
            atcoder.ResolutionError("http_403"),
            atcoder.ResolutionError("http_429"),
        ]
        out, _ = self.cli("resolve")
        self.assertIn("HTTP 429", out)
        self.assertEqual([r["status"] for r in self.records()], ["resolved", "pending", "pending", "pending"])
        self.assertEqual(self.fetch.call_count, 3)
        self.fetch.reset_mock(side_effect=True)
        self.fetch.return_value = note.parse_url(PROBLEM)
        self.cli("resolve")
        self.assertEqual([r["status"] for r in self.records()], ["resolved"] * 4)
        self.assertFalse(any("resolution_error" in row for row in self.records()))
        self.assertEqual([call.args[0] for call in self.fetch.call_args_list], [SECOND, THIRD, fourth])

    def test_missing_and_ambiguous_links_are_distinct_states(self):
        for url in (SUBMISSION, SECOND):
            self.cli("add", url)
        self.fetch.side_effect = [
            atcoder.ResolutionError("missing_task_link"),
            atcoder.ResolutionError("ambiguous_task_link", blocked=True),
        ]
        self.cli("resolve")
        self.assertEqual([r["status"] for r in self.records()], ["pending", "blocked"])
        self.assertTrue(all(row["task_id"] is None for row in self.records()))
        self.assertIn("問題リンクが複数ある", self.view.read_text(encoding="utf-8"))

    def test_same_task_id_with_different_problem_urls_is_not_grouped(self):
        self.cli("add", PROBLEM)
        self.cli("add", SUBMISSION)
        other_url = PROBLEM.replace("/example/", "/different/")
        self.fetch.side_effect = None
        self.fetch.return_value = note.parse_url(other_url)
        self.cli("resolve")
        problem, submission = self.records()
        self.assertEqual(problem["status"], "resolved")
        self.assertEqual(submission["status"], "blocked")
        self.assertEqual(submission["problem_url"], other_url)
        groups, remaining = note.group_inbox(self.records())
        self.assertFalse(groups)
        self.assertEqual({r["resolution_error"] for r in remaining}, {"task_conflict"})
        self.cli("resolve")
        self.fetch.assert_called_once_with(SUBMISSION)

    def test_duplicate_numeric_submission_ids_are_held_without_request(self):
        other_url = SUBMISSION.replace("/example/", "/different/").replace("900000001", "0900000001")
        for url in (SUBMISSION, other_url):
            self.cli("add", url)
        self.cli("resolve")
        self.fetch.assert_not_called()
        self.assertEqual([r["url"] for r in self.records()], [SUBMISSION, other_url])
        self.assertEqual({r["resolution_error"] for r in self.records()}, {"submission_conflict"})

    def test_existing_task_id_conflict_keeps_the_original_value(self):
        self.cli("add", SUBMISSION)
        record = {**self.records()[0], "task_id": "previous_a"}
        self.source.write_text(json.dumps(record) + "\n", encoding="utf-8")
        self.fetch.side_effect = None
        self.fetch.return_value = note.parse_url(PROBLEM)
        self.cli("resolve")
        record = self.records()[0]
        self.assertEqual(record["task_id"], "previous_a")
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(record["resolution_error"], "task_id_mismatch")
        self.assertNotIn("problem_url", record)

    def test_add_during_request_survives_the_resolver_save(self):
        self.cli("add", SUBMISSION)

        def register_during_fetch(url):
            self.assertEqual(url, SUBMISSION)
            self.cli("add", SECOND)
            return note.parse_url(PROBLEM)

        self.fetch.side_effect = register_during_fetch
        self.cli("resolve")
        self.assertEqual(
            [(r["url"], r["status"]) for r in self.records()],
            [(SUBMISSION, "resolved"), (SECOND, "pending")],
        )

    def test_original_is_safe_if_write_fails_and_view_rebuild_recovers(self):
        self.cli("add", SUBMISSION)
        original = self.source.read_bytes()
        self.fetch.side_effect = None
        self.fetch.return_value = note.parse_url(PROBLEM)
        with patch.object(note.os, "replace", side_effect=OSError("interrupted write")):
            self.cli("resolve", expected=1)
        self.assertEqual(self.source.read_bytes(), original)
        self.view.unlink()
        self.view.mkdir()
        self.cli("resolve", expected=1)
        self.assertEqual(self.records()[0]["status"], "resolved")
        self.view.rmdir()
        self.cli("resolve")
        self.assertIn(PROBLEM, self.view.read_text(encoding="utf-8"))
        self.assertEqual(self.fetch.call_count, 2)
