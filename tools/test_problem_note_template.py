from pathlib import Path
import unittest


class ProblemNoteTemplateTests(unittest.TestCase):
    def test_front_matter_uses_obsidian_format(self):
        vault = Path(__file__).resolve().parents[1]
        template = (vault / "管理" / "問題ノート雛形.md").read_text(encoding="utf-8")
        front_matter, closing_marker, _ = template.partition("\n---\n")

        self.assertTrue(closing_marker, "missing closing front matter delimiter")
        self.assertEqual(front_matter.splitlines(), [
            "---",
            "task_id:",
            "problem_url:",
            "submission_urls: []",
            "representative_submission_url:",
            "status: unorganized",
        ])
