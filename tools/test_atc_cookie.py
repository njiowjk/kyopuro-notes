from email.message import Message
from io import BytesIO, StringIO
import os
from pathlib import Path, PureWindowsPath
import stat
import sys
import tempfile
import traceback
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request

import atc_cookie
import atcoder
import note
from test_resolve import PROBLEM, SECOND, SUBMISSION, response


DUMMY_SESSION = "REVEL_SESSION=fixture-session-token"


@unittest.skipIf(os.name == "nt", "Unix credential permissions are POSIX-specific")
class UnixCookieTests(unittest.TestCase):
    def setUp(self):
        workspace = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(workspace)
        self.base = self.root / "state"
        self.cookie = self.base / "atc" / "cookie"
        self.cookie.parent.mkdir(parents=True)
        self.enterContext(patch.dict(os.environ, {"XDG_STATE_HOME": str(self.base), "HOME": workspace}))

    def store(self, payload):
        self.cookie.write_bytes(payload)
        self.cookie.chmod(0o600)

    def test_looks_under_xdg_and_uses_home_for_empty_or_relative_xdg(self):
        self.assertEqual(atc_cookie.cookie_location(), (self.base, ("atc",)))
        for override in ("", "relative"):
            with patch.dict(os.environ, {"XDG_STATE_HOME": override}):
                self.assertEqual(
                    atc_cookie.cookie_location(), (self.root / ".local" / "state", ("atc",))
                )
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.base / ".." / "outside")}):
            self.assertEqual(atc_cookie.load_session_cookie().state, "path")

    def test_missing_and_readonly_load_atc_rs_format(self):
        self.assertEqual(atc_cookie.load_session_cookie().state, "missing")
        self.assertFalse(self.cookie.exists())
        for ending in (b"", b"\n", b"\r\n"):
            with self.subTest(ending=ending):
                self.store(DUMMY_SESSION.encode() + ending)
                before = self.cookie.stat()
                session = atc_cookie.load_session_cookie()
                self.assertEqual(session.header, DUMMY_SESSION)
                self.assertNotIn(DUMMY_SESSION, repr(session))
                after = self.cookie.stat()
                self.assertEqual((before.st_mode, before.st_mtime_ns), (after.st_mode, after.st_mtime_ns))
                self.assertEqual(self.cookie.read_bytes(), DUMMY_SESSION.encode() + ending)
                self.assertEqual(list(self.cookie.parent.iterdir()), [self.cookie])

    def test_rejects_header_injection_and_invalid_or_oversized_payloads(self):
        for payload in (
            b"REVEL_SESSION=",
            b"Cookie: " + DUMMY_SESSION.encode(),
            DUMMY_SESSION.encode() + b"\r\nInjected: dummy",
            DUMMY_SESSION.encode() + b"; other=dummy",
            DUMMY_SESSION.encode() + b"\n\n",
            b"REVEL_SESSION=\xff",
            b"REVEL_SESSION=" + b"x" * 4096,
        ):
            self.store(payload)
            self.assertEqual(atc_cookie.load_session_cookie(), atc_cookie.SessionCookie("format"))

    def test_rejects_permissions_and_non_regular_paths(self):
        self.store(DUMMY_SESSION.encode())
        self.cookie.chmod(0o640)
        self.assertEqual(atc_cookie.load_session_cookie().state, "permissions")
        self.cookie.unlink()
        os.mkfifo(self.cookie, 0o600)
        self.assertEqual(atc_cookie.load_session_cookie().state, "path")
        self.cookie.unlink()
        self.cookie.mkdir()
        self.assertEqual(atc_cookie.load_session_cookie().state, "path")

    def test_rejects_symlinked_cookie_and_state_directory(self):
        outside = self.root / "alternate"
        outside.mkdir()
        destination = outside / "cookie"
        destination.write_text(DUMMY_SESSION, encoding="ascii")
        destination.chmod(0o600)
        self.cookie.symlink_to(destination)
        self.assertEqual(atc_cookie.load_session_cookie().state, "path")
        self.cookie.unlink()
        self.cookie.parent.rmdir()
        self.cookie.parent.symlink_to(outside, target_is_directory=True)
        self.assertEqual(atc_cookie.load_session_cookie().state, "path")


class CookieRequestTests(unittest.TestCase):
    def test_windows_appdata_location(self):
        with (
            patch.object(atc_cookie.sys, "platform", "win32"),
            patch.object(atc_cookie, "Path", PureWindowsPath),
            patch.dict(os.environ, {"APPDATA": r"C:\Users\example\AppData\Roaming"}),
        ):
            base, directories = atc_cookie.cookie_location()
            self.assertEqual(base.joinpath(*directories, "cookie"), PureWindowsPath(
                r"C:\Users\example\AppData\Roaming\atc\state\cookie"
            ))

    def test_windows_reader_rejects_reparse_points_before_open(self):
        directory = Mock(st_mode=stat.S_IFDIR, st_file_attributes=0)
        reparse_cookie = Mock(
            st_mode=stat.S_IFREG, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT
        )
        with (
            patch.object(Path, "lstat", side_effect=[directory, directory, reparse_cookie]),
            patch.object(Path, "open") as open_cookie,
        ):
            with self.assertRaises(OSError):
                atc_cookie.read_windows_cookie(Path("."), ("atc", "state"))
            open_cookie.assert_not_called()

    def test_only_valid_atcoder_submission_receives_cookie(self):
        session = atc_cookie.SessionCookie("loaded", DUMMY_SESSION)
        opener = Mock()
        opener.open.return_value = response()
        with patch.object(atcoder, "build_opener", return_value=opener):
            with self.assertRaises(atcoder.InvalidURL):
                atcoder.fetch_task(SUBMISSION.replace("atcoder.jp", "outside.example"), session=session)
            opener.open.assert_not_called()
            self.assertEqual(atcoder.fetch_task(SUBMISSION, session=session)["url"], PROBLEM)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.unredirected_hdrs["Cookie"], DUMMY_SESSION)
        self.assertEqual(request.full_url, SUBMISSION)

    def test_redirect_can_carry_cookie_only_after_origin_and_submission_validation(self):
        handler = atcoder.SubmissionRedirectHandler()
        original = Request(SUBMISSION)
        original.add_unredirected_header("Cookie", DUMMY_SESSION)
        for target in (
            SUBMISSION.replace("atcoder.jp", "outside.example"),
            SUBMISSION.replace("https:", "http:"),
            "https://atcoder.jp/login",
            SECOND,
        ):
            with self.subTest(target=target), self.assertRaises(atcoder.ResolutionError):
                handler.redirect_request(original, BytesIO(), 302, "", {}, target)
        redirected = handler.redirect_request(original, BytesIO(), 302, "", {}, SUBMISSION + "?lang=ja")
        self.assertEqual(redirected.unredirected_hdrs["Cookie"], DUMMY_SESSION)

    def test_raw_transport_errors_and_headers_are_not_chained(self):
        session = atc_cookie.SessionCookie("loaded", DUMMY_SESSION)
        headers = Message()
        headers["Set-Cookie"] = DUMMY_SESSION
        for failure, expected in (
            (HTTPError(SUBMISSION, 403, DUMMY_SESSION, headers, BytesIO()), "http_403"),
            (ValueError(f"invalid header {DUMMY_SESSION}"), "network"),
        ):
            opener = Mock()
            opener.open.side_effect = failure
            with patch.object(atcoder, "build_opener", return_value=opener):
                with self.assertRaises(atcoder.ResolutionError) as raised:
                    atcoder.fetch_task(SUBMISSION, session=session)
            error = raised.exception
            self.assertEqual(str(error), expected)
            self.assertIsNone(error.__context__)
            self.assertNotIn(DUMMY_SESSION, "".join(traceback.format_exception(error)))


class CookieResolveTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(note, "VAULT", self.root))
        self.original = self.root / ".local" / "inbox.jsonl"
        self.loader = self.enterContext(patch.object(note, "load_session_cookie"))
        self.fetch = self.enterContext(patch.object(note, "fetch_task"))

    def cli(self, *args):
        with (
            patch.object(sys, "argv", ["note.py", *args]),
            patch.object(sys, "stdout", new_callable=StringIO) as out,
            patch.object(sys, "stderr", new_callable=StringIO) as err,
        ):
            self.assertEqual(note.main(), 0, err.getvalue())
        return out.getvalue(), err.getvalue()

    def test_add_and_local_views_do_not_read_credentials_or_access_network(self):
        self.loader.side_effect = AssertionError("unexpected credential read")
        self.fetch.side_effect = AssertionError("unexpected network request")
        self.cli("resolve")
        self.cli("add", SUBMISSION)
        self.cli("list")
        self.cli("rebuild")
        self.loader.assert_not_called()
        self.fetch.assert_not_called()

    def test_403_diagnoses_only_observed_state_and_keeps_pending_records(self):
        self.cli("add", SUBMISSION)
        before, = note.read_records(self.original)
        for session, expected in (
            (atc_cookie.SessionCookie("loaded", DUMMY_SESSION), "認証情報を送信"),
            (atc_cookie.SessionCookie("missing"), "見つからず"),
            (atc_cookie.SessionCookie("permissions"), "読み込めず"),
        ):
            self.fetch.reset_mock()
            self.loader.return_value = session
            self.fetch.side_effect = atcoder.ResolutionError("http_403")
            out, err = self.cli("resolve")
            self.assertIn(expected, out)
            self.assertIn("原因やセッションの有効性は確認できません", out)
            if session.header:
                self.fetch.assert_called_once_with(SUBMISSION, session=session)
            else:
                self.fetch.assert_called_once_with(SUBMISSION)
            current, = note.read_records(self.original)
            self.assertEqual(current["status"], "pending")
            self.assertEqual(current["url"], before["url"])
            self.assertEqual(current["registered_at"], before["registered_at"])
            view = (self.root / "Inbox.md").read_text(encoding="utf-8")
            self.assertNotIn(DUMMY_SESSION, out + err + self.original.read_text(encoding="utf-8") + view)
        self.loader.return_value = atc_cookie.SessionCookie("loaded", DUMMY_SESSION)
        self.fetch.side_effect = None
        self.fetch.return_value = note.parse_url(PROBLEM)
        self.cli("resolve")
        self.assertEqual(note.read_records(self.original)[0]["status"], "resolved")
