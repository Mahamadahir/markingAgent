import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
import contextlib
import io
from types import SimpleNamespace
from unittest import mock

from marking_agent import app_service, cli
from marking_agent.app_service import AppService, normalise_action
from marking_agent.state import OVERRIDDEN

from marking_agent.config import CSV_FIELDNAMES
from marking_agent.grading import build_pdf_dispatch_text, validate_evaluation, validate_score_range
from marking_agent.providers import build_openai_content
from marking_agent.mark_scheme import extract_mark_scheme_snippet, list_question_ids
from marking_agent.pdf_submissions import (
    FULL_SCRIPT_QUESTION_ID,
    expand_submissions_by_question,
    image_data_url,
    load_pdf_submissions,
)
from marking_agent.state import (
    AI_GENERATED,
    APPROVED,
    connect_database,
    create_exam,
    evaluation_from_record,
    get_record,
    initialise_database,
    is_final_record,
    iter_records,
    save_human_decision,
    save_provisional_evaluation,
)
from marking_agent.storage import build_csv_row, export_records_to_csv


class MarkSchemeTests(unittest.TestCase):
    def test_extracts_matching_question_section(self):
        mark_scheme = "# Q1\nOne\n\n# Q2\nTwo\n\n# Q3\nThree"

        snippet = extract_mark_scheme_snippet(mark_scheme, "Q2")

        self.assertEqual(snippet, "# Q2\nTwo")

    def test_accepts_question_word_heading(self):
        mark_scheme = "Question 1\nOne\n\nQuestion 2\nTwo"

        snippet = extract_mark_scheme_snippet(mark_scheme, "Q1")

        self.assertEqual(snippet, "Question 1\nOne")

    def test_falls_back_to_full_mark_scheme_when_no_heading_matches(self):
        mark_scheme = "General marking notes"

        snippet = extract_mark_scheme_snippet(mark_scheme, "Q9")

        self.assertEqual(snippet, mark_scheme)

    def test_lists_question_ids_in_order_without_duplicates(self):
        mark_scheme = "# Q1\nOne\n\n# Q2\nTwo\n\n# Q1\nMore of one"

        self.assertEqual(list_question_ids(mark_scheme), ["Q1", "Q2"])

    def test_lists_no_questions_when_no_headings(self):
        self.assertEqual(list_question_ids("General marking notes"), [])


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


class ProviderTests(unittest.TestCase):
    def test_builds_openai_provider_by_default(self):
        from marking_agent.config import provider_settings
        from marking_agent.providers import OpenAIProvider, build_provider

        provider = build_provider(provider_settings("gpt-4o", provider="openai"))

        self.assertIsInstance(provider, OpenAIProvider)
        self.assertEqual(provider.model, "gpt-4o")

    def test_builds_azure_provider_with_deployment_as_model(self):
        from marking_agent.config import provider_settings
        from marking_agent.providers import AzureOpenAIProvider, build_provider

        settings = provider_settings(
            "grading-deployment",
            provider="azure",
            azure_endpoint="https://example.openai.azure.com",
            azure_api_version="2024-08-01-preview",
        )
        provider = build_provider(settings)

        self.assertIsInstance(provider, AzureOpenAIProvider)
        self.assertEqual(provider.model, "grading-deployment")

    def test_builds_anthropic_and_gemini_providers(self):
        from marking_agent.config import provider_settings
        from marking_agent.providers import AnthropicProvider, GeminiProvider, build_provider

        anthropic = build_provider(provider_settings("claude-opus-4-8", provider="anthropic"))
        gemini = build_provider(provider_settings("gemini-1.5-pro", provider="gemini"))

        self.assertIsInstance(anthropic, AnthropicProvider)
        self.assertIsInstance(gemini, GeminiProvider)

    def test_rejects_unknown_provider(self):
        from marking_agent.config import provider_settings
        from marking_agent.providers import build_provider

        with self.assertRaises(ValueError):
            build_provider(provider_settings("gpt-4o", provider="mistral"))

    def test_splits_data_url_into_media_type_and_payload(self):
        from marking_agent.providers import split_data_url

        media_type, encoded = split_data_url("data:image/png;base64,QUJD")

        self.assertEqual(media_type, "image/png")
        self.assertEqual(encoded, "QUJD")


class ValidationTests(unittest.TestCase):
    def test_score_cannot_exceed_total_marks(self):
        with self.assertRaises(ValueError):
            validate_score_range(Decimal("4"), Decimal("3"))

    def test_validates_model_result_identity(self):
        evaluation = {
            "student_id": "STUDENT_001",
            "question_id": "Q1",
            "total_marks_available": 2,
            "proposed_marks_awarded": 1,
        }

        validate_evaluation(evaluation, "STUDENT_001", "Q1")

    def test_rejects_mismatched_model_result_identity(self):
        evaluation = {
            "student_id": "STUDENT_002",
            "question_id": "Q1",
            "total_marks_available": 2,
            "proposed_marks_awarded": 1,
        }

        with self.assertRaises(ValueError):
            validate_evaluation(evaluation, "STUDENT_001", "Q1")


class StorageTests(unittest.TestCase):
    def test_build_csv_row_serialises_structured_evaluation(self):
        evaluation = sample_evaluation()

        row = build_csv_row("STUDENT_001", "Q1", evaluation, "APPROVED", "2", "Approved", "exam-1", "Biology")

        self.assertEqual(row["Exam ID"], "exam-1")
        self.assertEqual(row["Exam Name"], "Biology")
        self.assertEqual(json.loads(row["Provisional AI Output"]), evaluation)

    def test_exports_final_records_to_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "state.sqlite3"
            csv_path = Path(directory) / "grading_output.csv"
            connection = create_test_database(db_path)
            save_human_decision(
                connection,
                "default",
                "STUDENT_001",
                "Q1",
                sample_evaluation(),
                APPROVED,
                "2",
                "Approved AI assessment.",
            )

            export_records_to_csv(iter_records(connection, final_only=True), csv_path)

            with csv_path.open("r", newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(rows[0]["Exam ID"], "default")
            self.assertEqual(rows[0]["Student ID"], "STUDENT_001")
            self.assertEqual(rows[0]["Human Action"], APPROVED)
            self.assertEqual(rows[0]["Final Score"], "2")


class StateTests(unittest.TestCase):
    def test_saves_provisional_evaluation_before_human_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = create_test_database(Path(directory) / "state.sqlite3")

            save_provisional_evaluation(connection, "default", "STUDENT_001", "Q1", sample_evaluation())
            record = get_record(connection, "default", "STUDENT_001", "Q1")

            self.assertEqual(record["status"], AI_GENERATED)
            self.assertEqual(evaluation_from_record(record), sample_evaluation())
            self.assertFalse(is_final_record(record))

    def test_updates_provisional_record_with_human_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = create_test_database(Path(directory) / "state.sqlite3")
            save_provisional_evaluation(connection, "default", "STUDENT_001", "Q1", sample_evaluation())

            save_human_decision(
                connection,
                "default",
                "STUDENT_001",
                "Q1",
                sample_evaluation(),
                APPROVED,
                "2",
                "Approved AI assessment.",
            )
            record = get_record(connection, "default", "STUDENT_001", "Q1")

            self.assertTrue(is_final_record(record))
            self.assertEqual(record["status"], APPROVED)
            self.assertEqual(record["final_score"], "2")

    def test_final_record_is_not_overwritten_by_provisional_resume_save(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = create_test_database(Path(directory) / "state.sqlite3")
            save_human_decision(
                connection,
                "default",
                "STUDENT_001",
                "Q1",
                sample_evaluation(),
                APPROVED,
                "2",
                "Approved AI assessment.",
            )
            changed = sample_evaluation()
            changed["proposed_marks_awarded"] = 1

            save_provisional_evaluation(connection, "default", "STUDENT_001", "Q1", changed)
            record = get_record(connection, "default", "STUDENT_001", "Q1")

            self.assertEqual(record["status"], APPROVED)
            self.assertEqual(evaluation_from_record(record)["proposed_marks_awarded"], 2)

    def test_records_are_isolated_by_exam(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = create_test_database(Path(directory) / "state.sqlite3")
            biology_id = create_exam(connection, "Biology Paper 1", exam_id="biology")
            chemistry_id = create_exam(connection, "Chemistry Paper 1", exam_id="chemistry")

            save_provisional_evaluation(connection, biology_id, "STUDENT_001", "Q1", sample_evaluation())
            changed = sample_evaluation()
            changed["proposed_marks_awarded"] = 1
            save_provisional_evaluation(connection, chemistry_id, "STUDENT_001", "Q1", changed)

            biology_record = get_record(connection, biology_id, "STUDENT_001", "Q1")
            chemistry_record = get_record(connection, chemistry_id, "STUDENT_001", "Q1")

            self.assertEqual(evaluation_from_record(biology_record)["proposed_marks_awarded"], 2)
            self.assertEqual(evaluation_from_record(chemistry_record)["proposed_marks_awarded"], 1)



class FakeProvider:
    def __init__(self, evaluation):
        self._payload = json.dumps(evaluation)
        self.calls = []

    def complete_json(self, system_prompt, user_text, image_data_urls=None):
        self.calls.append((system_prompt, user_text, image_data_urls))
        return self._payload


def write_submissions(directory):
    (directory / "STUDENT_001.pdf").write_bytes(b"pdf")
    (directory / "STUDENT_002.pdf").write_bytes(b"pdf")


def full_script_evaluation(student_id, marks=2):
    evaluation = sample_evaluation()
    evaluation["student_id"] = student_id
    evaluation["question_id"] = FULL_SCRIPT_QUESTION_ID
    evaluation["proposed_marks_awarded"] = marks
    return evaluation


class NormaliseActionTests(unittest.TestCase):
    def test_maps_verb_forms_to_status_constants(self):
        self.assertEqual(normalise_action("approve"), APPROVED)
        self.assertEqual(normalise_action(" override "), OVERRIDDEN)

    def test_accepts_status_constants_directly(self):
        self.assertEqual(normalise_action(APPROVED), APPROVED)
        self.assertEqual(normalise_action(OVERRIDDEN), OVERRIDDEN)

    def test_rejects_unknown_action(self):
        with self.assertRaises(ValueError):
            normalise_action("reject")


class AppServiceTests(unittest.TestCase):
    def build_service(self, directory):
        service = AppService(
            db_path=directory / "state.sqlite3",
            output_path=directory / "grades.csv",
            exam_name="Paper 1",
        )
        self.addCleanup(service.close)
        return service

    def test_creates_and_lists_default_exam(self):
        with tempfile.TemporaryDirectory() as raw:
            service = self.build_service(Path(raw))

            self.assertTrue(any(exam["exam_id"] == service.exam_id for exam in service.exams()))

    def test_set_exam_switches_active_exam(self):
        with tempfile.TemporaryDirectory() as raw:
            service = self.build_service(Path(raw))

            chemistry_id = service.set_exam(exam_id="chemistry", exam_name="Chemistry")

            self.assertEqual(service.exam_id, chemistry_id)
            self.assertEqual(chemistry_id, "chemistry")

    def test_load_exam_items_reports_pending_status(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            write_submissions(directory)
            service = self.build_service(directory)

            items = service.load_exam_items(directory)

            self.assertEqual([item["student_id"] for item in items], ["STUDENT_001", "STUDENT_002"])
            self.assertEqual({item["status"] for item in items}, {"PENDING"})

    def test_grade_item_saves_provisional_evaluation(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            write_submissions(directory)
            mark_scheme_path = directory / "scheme.txt"
            mark_scheme_path.write_text("Full script guidance", encoding="utf-8")
            service = self.build_service(directory)
            item = service.load_exam_items(directory)[0]

            settings = object()
            with mock.patch.object(app_service, "build_provider", return_value=FakeProvider(full_script_evaluation("STUDENT_001"))):
                with mock.patch.object(app_service, "grade_pdf_response", return_value=full_script_evaluation("STUDENT_001")) as graded:
                    evaluation = service.grade_item(settings, mark_scheme_path, item)

            self.assertEqual(evaluation["student_id"], "STUDENT_001")
            graded.assert_called_once()
            self.assertEqual(service.get_saved_evaluation("STUDENT_001", FULL_SCRIPT_QUESTION_ID)["proposed_marks_awarded"], 2)

    def test_grade_item_resumes_saved_evaluation_without_regrading(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            write_submissions(directory)
            mark_scheme_path = directory / "scheme.txt"
            mark_scheme_path.write_text("guidance", encoding="utf-8")
            service = self.build_service(directory)
            item = service.load_exam_items(directory)[0]
            save_provisional_evaluation(service.connection, service.exam_id, "STUDENT_001", FULL_SCRIPT_QUESTION_ID, full_script_evaluation("STUDENT_001", marks=1))

            with mock.patch.object(app_service, "grade_pdf_response") as graded:
                evaluation = service.grade_item(object(), mark_scheme_path, item)

            graded.assert_not_called()
            self.assertEqual(evaluation["proposed_marks_awarded"], 1)

    def test_save_decision_validates_and_exports_csv(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            service = self.build_service(directory)
            evaluation = full_script_evaluation("STUDENT_001")

            normalised = service.save_decision("STUDENT_001", FULL_SCRIPT_QUESTION_ID, evaluation, APPROVED, "2", "Approved AI assessment.")

            self.assertEqual(normalised, "2")
            self.assertTrue((directory / "grades.csv").exists())
            self.assertEqual(len(service.records(final_only=True)), 1)

    def test_save_decision_rejects_out_of_range_score(self):
        with tempfile.TemporaryDirectory() as raw:
            service = self.build_service(Path(raw))
            evaluation = full_script_evaluation("STUDENT_001")

            with self.assertRaises(ValueError):
                service.save_decision("STUDENT_001", FULL_SCRIPT_QUESTION_ID, evaluation, APPROVED, "9", "note")


class QuietStdoutMixin:
    def setUp(self):
        redirect = contextlib.redirect_stdout(io.StringIO())
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)


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

            with mock.patch.object(cli, "grade_pdf_response", return_value=sample_evaluation()) as graded:
                result = cli.get_or_create_evaluation(connection, "default", args, None, submission, "scheme")

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


def sample_evaluation():
    return {
        "student_id": "STUDENT_001",
        "question_id": "Q1",
        "deviation_detected": False,
        "deviation_notes": "",
        "total_marks_available": 2,
        "proposed_marks_awarded": 2,
        "criteria_breakdown": [],
    }


def create_test_database(path):
    connection = connect_database(path)
    initialise_database(connection)
    return connection


if __name__ == "__main__":
    unittest.main()
