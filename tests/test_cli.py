import contextlib
import io
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from marking_agent import cli
from marking_agent.pdf_submissions import FULL_SCRIPT_QUESTION_ID
from marking_agent.state import (
    APPROVED,
    OVERRIDDEN,
    get_record,
    save_human_decision,
    save_provisional_evaluation,
    set_question_topics,
)
from tests.helpers import QuietStdoutMixin, create_test_database, sample_evaluation


class AnalyticsCommandTests(unittest.TestCase):
    def _run(self, db_path):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cli.analytics_command(SimpleNamespace(db=str(db_path), exam_id=""))
        return buffer.getvalue()

    def test_reports_no_finalised_grades(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            create_test_database(path).close()

            self.assertIn("No finalised grades", self._run(path))

    def test_reports_question_and_topic_statistics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            connection = create_test_database(path)
            save_human_decision(connection, "default", "STUDENT_001", "Q1", sample_evaluation(), APPROVED, "2", "note")
            set_question_topics(connection, "default", {"Q1": "Photosynthesis"})
            connection.close()

            output = self._run(path)

            self.assertIn("Q1", output)
            self.assertIn("Photosynthesis", output)


class CliLogicTests(QuietStdoutMixin, unittest.TestCase):
    def test_mark_scheme_for_question_returns_full_script_unchanged(self):
        mark_scheme = "# Q1\nOne\n\n# Q2\nTwo"

        self.assertEqual(cli.mark_scheme_for_question(mark_scheme, FULL_SCRIPT_QUESTION_ID), mark_scheme)

    def test_mark_scheme_for_question_returns_matching_snippet(self):
        mark_scheme = "# Q1\nOne\n\n# Q2\nTwo"

        self.assertEqual(cli.mark_scheme_for_question(mark_scheme, "Q2"), "# Q2\nTwo")

    def test_get_or_create_evaluation_skips_finalised_record(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = create_test_database(Path(directory) / "state.sqlite3")
            self.addCleanup(connection.close)
            save_human_decision(connection, "default", "STUDENT_001", FULL_SCRIPT_QUESTION_ID, sample_evaluation(), APPROVED, "2", "note")
            submission = {"student_id": "STUDENT_001", "question_id": FULL_SCRIPT_QUESTION_ID, "pdf_path": "a.pdf"}
            args = SimpleNamespace(no_resume=False)

            result = cli.get_or_create_evaluation(connection, "default", args, None, submission, "scheme")

            self.assertIsNone(result)

    def test_get_or_create_evaluation_resumes_provisional_record(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = create_test_database(Path(directory) / "state.sqlite3")
            self.addCleanup(connection.close)
            save_provisional_evaluation(connection, "default", "STUDENT_001", FULL_SCRIPT_QUESTION_ID, sample_evaluation())
            submission = {"student_id": "STUDENT_001", "question_id": FULL_SCRIPT_QUESTION_ID, "pdf_path": "a.pdf"}
            args = SimpleNamespace(no_resume=False)

            result = cli.get_or_create_evaluation(connection, "default", args, None, submission, "scheme")

            self.assertEqual(result["proposed_marks_awarded"], 2)

    def test_get_or_create_evaluation_grades_new_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = create_test_database(Path(directory) / "state.sqlite3")
            self.addCleanup(connection.close)
            submission = {"student_id": "STUDENT_001", "question_id": FULL_SCRIPT_QUESTION_ID, "pdf_path": "a.pdf"}
            args = SimpleNamespace(no_resume=False)

            resolver = SimpleNamespace(provider=object(), pages_for=lambda pdf_path, question_id: ["page"])
            with mock.patch.object(cli, "grade_pdf_images", return_value=sample_evaluation()) as graded:
                result = cli.get_or_create_evaluation(connection, "default", args, resolver, submission, "scheme")

            graded.assert_called_once()
            self.assertEqual(result["proposed_marks_awarded"], 2)
            self.assertIsNotNone(get_record(connection, "default", "STUDENT_001", FULL_SCRIPT_QUESTION_ID))

    def test_export_finalised_records_counts_written_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = create_test_database(Path(directory) / "state.sqlite3")
            self.addCleanup(connection.close)
            save_human_decision(connection, "default", "STUDENT_001", FULL_SCRIPT_QUESTION_ID, sample_evaluation(), APPROVED, "2", "note")

            count = cli.export_finalised_records(connection, Path(directory) / "out.csv", exam_id="default")

            self.assertEqual(count, 1)


class CliPromptTests(QuietStdoutMixin, unittest.TestCase):
    def test_prompt_action_accepts_approve(self):
        with mock.patch("builtins.input", return_value="approve"):
            self.assertEqual(cli.prompt_action(), APPROVED)

    def test_prompt_action_reprompts_until_valid(self):
        with mock.patch("builtins.input", side_effect=["maybe", "override"]):
            self.assertEqual(cli.prompt_action(), OVERRIDDEN)

    def test_prompt_score_uses_default_on_blank_input(self):
        with mock.patch("builtins.input", return_value=""):
            self.assertEqual(cli.prompt_score("Score", Decimal("5"), default="3"), "3")

    def test_prompt_score_rejects_out_of_range_then_accepts(self):
        with mock.patch("builtins.input", side_effect=["9", "4"]):
            self.assertEqual(cli.prompt_score("Score", Decimal("5")), "4")

    def test_prompt_override_reason_requires_non_empty(self):
        with mock.patch("builtins.input", side_effect=["", "Marker disagreed"]):
            self.assertEqual(cli.prompt_override_reason(), "Marker disagreed")


class CliCommandTests(QuietStdoutMixin, unittest.TestCase):
    def test_main_returns_error_code_on_known_failure(self):
        args = SimpleNamespace(command="grade")
        with mock.patch.object(cli, "parse_args", return_value=args):
            with mock.patch.object(cli, "grade_all", side_effect=FileNotFoundError("missing")):
                self.assertEqual(cli.main(), 1)

    def test_main_dispatches_list_exams_command(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "state.sqlite3"
            create_test_database(db_path).close()
            args = SimpleNamespace(command="list-exams", db=str(db_path))
            with mock.patch.object(cli, "parse_args", return_value=args):
                self.assertEqual(cli.main(), 0)

    def test_export_csv_command_writes_output(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "state.sqlite3"
            connection = create_test_database(db_path)
            save_human_decision(connection, "default", "STUDENT_001", FULL_SCRIPT_QUESTION_ID, sample_evaluation(), APPROVED, "2", "note")
            connection.close()
            output_path = Path(directory) / "out.csv"
            args = SimpleNamespace(db=str(db_path), output=str(output_path), exam_id="", all_exams=True)

            cli.export_csv_command(args)

            self.assertTrue(output_path.exists())


if __name__ == "__main__":
    unittest.main()
