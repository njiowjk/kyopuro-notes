from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import atc_source
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

WINDOWS_CLI = """from test_note import windows_atc_fixture
import note

with windows_atc_fixture():
    raise SystemExit(note.main())
"""


def windows_atc_fixture():
    # Windows では拡張子なしの atc 呼び出しで .cmd を起動できない。
    def run_atc(command, **options):
        executable, *arguments = command
        if executable != "atc":
            raise AssertionError(f"想定外のコマンド: {executable}")
        script = Path(os.environ["PATH"]) / executable
        if not script.is_file():
            raise FileNotFoundError(script)
        return subprocess.run([sys.executable, "-B", script, *arguments], **options)

    runner = SimpleNamespace(run=run_atc, TimeoutExpired=subprocess.TimeoutExpired)
    return patch.object(atc_source, "subprocess", runner)


class InboxFixture:
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name).resolve()
        self.tools = self.root / "tools"
        self.tools.mkdir()
        source = Path(note.__file__).parent
        for filename in ("note.py", "atcoder.py", "atc_source.py", "domain_links.py"):
            shutil.copyfile(source / filename, self.tools / filename)
        self.workspace = self.root / "Workspace root"
        self.workspace.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.atc = self.bin / "atc"
        self.fixture = self.root / "atc.json"
        self.fixture.write_text("{}", encoding="utf-8")
        self.cli_script = self.tools / "note.py"
        if os.name == "nt":
            self.atc.write_text(FAKE_ATC, encoding="utf-8")
            shutil.copyfile(__file__, self.tools / "test_note.py")
            self.cli_script = self.tools / "run_note.py"
            self.cli_script.write_text(WINDOWS_CLI, encoding="utf-8")
            self.enterContext(windows_atc_fixture())
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
            [sys.executable, "-B", self.cli_script, *args],
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


class DomainLinksTests(InboxFixture, unittest.TestCase):
    BEGIN = "<!-- BEGIN AUTO: domain-solutions -->"
    END = "<!-- END AUTO: domain-solutions -->"

    def write(self, path, content):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content.encode("utf-8"))
        return file

    def link(self, name, target):
        return f"- [{name}]({target})\n"

    def write_catalog(self, *links):
        return self.write("管理/解法ノート一覧.md", "# 解法ノート一覧\n\n" + "".join(links))

    def test_sync_uses_catalog_only_and_can_add_later_without_touching_inbox(self):
        begin, end = self.BEGIN, self.END
        before = f"# 文字列\n\n手書きの説明\n\n{begin}\n"
        after = f"{end}\n\n手書きの追記\n"
        index = self.write(
            "分野/文字列/文字列.md",
            before + "\n- [古い項目](古い項目.md)\n\n" + after,
        )
        for name in ("Z", "A #1", "B"):
            self.write(f"分野/文字列/{name}.md", f"# {name}\n")
        self.write("分野/木/木の走査.md", "# 木の走査\n")
        self.write("分野/整数/整数の集計.md", "# 整数の集計\n")
        unmanaged = self.write("分野/整数/整数.md", "# 整数\n")
        proposals = self.write(
            "管理/追加候補.md",
            "## B\n\n- 状態　作成済み\n- 主分野・保存先　[B](../分野/文字列/B.md)\n",
        )
        catalog = self.write_catalog(
            self.link("Z", "../分野/文字列/Z.md"),
            self.link("A #1", "../分野/文字列/A%20%231.md"),
            self.link("Zの再登録", "../分野/文字列/./Z.md"),
            self.link("木の走査", "../分野/木/木の走査.md"),
            self.link("整数の集計", "../分野/整数/整数の集計.md"),
        )
        self.assertIn("整数, 木", self.cli("sync-domain-links").stdout)
        self.assertEqual(
            index.read_bytes().decode("utf-8"),
            before + "\n- [A #1](A%20%231.md)\n- [Z](Z.md)\n\n" + after,
        )
        original_mtime = index.stat().st_mtime_ns
        self.assertIn("0件", self.cli("sync-domain-links").stdout)
        self.assertEqual(index.stat().st_mtime_ns, original_mtime)

        proposals.unlink()
        with catalog.open("ab") as stream:
            stream.write(self.link("B", "../分野/文字列/B.md").encode("utf-8"))
        self.assertIn("1件", self.cli("sync-domain-links").stdout)
        self.assertIn(b"- [B](B.md)\n", index.read_bytes())
        self.assertIn("0件", self.cli("sync-domain-links").stdout)
        self.assertEqual(unmanaged.read_text(encoding="utf-8"), "# 整数\n")
        self.assertFalse((self.root / "分野/木/木.md").exists())
        self.assertFalse(self.source.parent.exists())
        self.assertFalse(self.view.exists())

    def test_sync_preserves_handwritten_links_line_endings_and_permissions(self):
        manual = (
            "# 文字列\r\n\r\n"
            "- [手動で参照](./A%20B.md#節)\r\n"
            "- [[分野/文字列/C|別名]]\r\n"
            "- [Unicodeの別表記](か\u3099.md)\r\n\r\n"
            "```md\r\n- [記法の例](D.md)\r\n```\r\n\r\n"
        )
        index = self.write("分野/文字列/文字列.md", manual + f"{self.BEGIN}\r\n\r\n{self.END}")
        before_mode = index.stat().st_mode
        for name in ("A B", "C", "D", "が"):
            self.write(f"分野/文字列/{name}.md", "# 解法\n")
        self.write_catalog(*(
            self.link(name, f"../分野/文字列/{link}.md")
            for name, link in (("A B", "A%20B"), ("C", "C"), ("D", "D"), ("が", "が"))
        ))
        self.cli("sync-domain-links")
        self.assertEqual(
            index.read_bytes().decode("utf-8"),
            manual + f"{self.BEGIN}\r\n\r\n- [D](D.md)\r\n\r\n{self.END}",
        )
        self.assertEqual(index.stat().st_mode, before_mode)

    def test_sync_rejects_wrong_missing_or_non_solution_targets_before_writing(self):
        content = f"# 配列\n\n{self.BEGIN}\n\n{self.END}\n"
        index = self.write("分野/配列/配列.md", content)
        self.write("分野/配列/OK.md", "# OK\n")
        self.write("アルゴリズム/外部.md", "# 外部\n")
        valid = self.link("OK", "../分野/配列/OK.md")
        for name, path in (
            ("欠落", "../分野/配列/欠落.md"),
            ("外部", "../アルゴリズム/外部.md"),
            ("入口", "../分野/配列/配列.md"),
            ("分野/グラフ/OK.md", "../分野/配列/OK.md"),
            ("節", "../分野/配列/OK.md#節"),
        ):
            with self.subTest(name=name):
                self.write_catalog(valid, self.link(name, path))
                self.cli("sync-domain-links", code=1)
                self.assertEqual(index.read_text(encoding="utf-8"), content)

    def test_sync_rejects_broken_markers_or_handwritten_content_inside_list(self):
        self.write_catalog()
        for markers in (
            self.BEGIN,
            f"{self.BEGIN}\n{self.BEGIN}\n{self.END}",
            f"{self.END}\n{self.BEGIN}",
            f"{self.BEGIN}\n手書きの説明\n{self.END}",
        ):
            with self.subTest(markers=markers):
                original = f"# 文字列\n\n{markers}\n"
                index = self.write("分野/文字列/文字列.md", original)
                self.cli("sync-domain-links", code=1)
                self.assertEqual(index.read_text(encoding="utf-8"), original)

    def test_sync_preserves_existing_list_if_catalog_is_missing_or_malformed(self):
        content = f"# 配列\n\n{self.BEGIN}\n\n- [OK](OK.md)\n\n{self.END}\n"
        index = self.write("分野/配列/配列.md", content)
        self.write("分野/配列/OK.md", "# OK\n")
        self.cli("sync-domain-links", code=1)
        self.assertEqual(index.read_text(encoding="utf-8"), content)
        for bad_catalog in ("", "# 間違った見出し\n", "# 解法ノート一覧\n\n- [[OK]]\n"):
            with self.subTest(catalog=bad_catalog):
                self.write("管理/解法ノート一覧.md", bad_catalog)
                self.cli("sync-domain-links", code=1)
                self.assertEqual(index.read_text(encoding="utf-8"), content)


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
