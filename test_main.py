import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from marking_agent.config import CSV_FIELDNAMES
from marking_agent.grading import build_pdf_dispatch_text, validate_evaluation, validate_score_range
from marking_agent.providers import build_openai_content
from marking_agent.mark_scheme import extract_mark_scheme_snippet
from marking_agent.pdf_submissions import FULL_SCRIPT_QUESTION_ID, image_data_url, load_pdf_submissions
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
