import tempfile
import unittest
from pathlib import Path

from marking_agent.grading import build_pdf_dispatch_text
from marking_agent.pdf_submissions import (
    FULL_SCRIPT_QUESTION_ID,
    expand_submissions_by_question,
    image_data_url,
    load_pdf_submissions,
)
from marking_agent.providers import build_openai_content


class PdfSubmissionTests(unittest.TestCase):
    def test_loads_pdf_submissions_from_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "STUDENT_002.pdf").write_bytes(b"pdf")
            (path / "STUDENT_001.pdf").write_bytes(b"pdf")
            (path / "notes.txt").write_text("ignore", encoding="utf-8")

            submissions = load_pdf_submissions(path)

            self.assertEqual([item["student_id"] for item in submissions], ["STUDENT_001", "STUDENT_002"])
            self.assertEqual(submissions[0]["question_id"], FULL_SCRIPT_QUESTION_ID)

    def test_loads_single_pdf_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "STUDENT_001.pdf"
            path.write_bytes(b"pdf")

            submissions = load_pdf_submissions(path)

            self.assertEqual(submissions, [{"student_id": "STUDENT_001", "question_id": FULL_SCRIPT_QUESTION_ID, "pdf_path": str(path)}])

    def test_expands_one_submission_into_one_item_per_question(self):
        submissions = [{"student_id": "STUDENT_001", "question_id": FULL_SCRIPT_QUESTION_ID, "pdf_path": "a.pdf"}]

        items = expand_submissions_by_question(submissions, ["Q1", "Q2"])

        self.assertEqual(
            [(item["student_id"], item["question_id"], item["pdf_path"]) for item in items],
            [("STUDENT_001", "Q1", "a.pdf"), ("STUDENT_001", "Q2", "a.pdf")],
        )

    def test_expansion_is_a_noop_without_questions(self):
        submissions = [{"student_id": "STUDENT_001", "question_id": FULL_SCRIPT_QUESTION_ID, "pdf_path": "a.pdf"}]

        self.assertEqual(expand_submissions_by_question(submissions, []), submissions)

    def test_builds_pdf_image_dispatch_content(self):
        image_url = image_data_url(b"image-bytes", "image/png")
        user_text = build_pdf_dispatch_text("STUDENT_001", FULL_SCRIPT_QUESTION_ID, "scheme")

        content = build_openai_content(user_text, [image_url])

        self.assertEqual(content[0]["type"], "text")
        self.assertIn("scheme", content[0]["text"])
        self.assertEqual(content[1], {"type": "image_url", "image_url": {"url": image_url}})


if __name__ == "__main__":
    unittest.main()
