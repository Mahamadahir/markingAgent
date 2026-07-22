import tempfile
import unittest
from pathlib import Path

import sqlite3

from marking_agent.state import (
    AI_GENERATED,
    APPROVED,
    create_exam,
    evaluation_from_record,
    get_exam,
    get_record,
    initialise_database,
    is_final_record,
    save_human_decision,
    save_provisional_evaluation,
    set_exam_provider,
)
from tests.helpers import create_test_database, sample_evaluation


class ExamProviderTests(unittest.TestCase):
    def test_create_exam_persists_provider_and_model(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = create_test_database(Path(directory) / "state.sqlite3")
            exam_id = create_exam(connection, "Biology", provider="anthropic", model="claude-opus-4-8")

            exam = get_exam(connection, exam_id)

            self.assertEqual(exam["provider"], "anthropic")
            self.assertEqual(exam["model"], "claude-opus-4-8")

    def test_set_exam_provider_updates_existing_exam(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = create_test_database(Path(directory) / "state.sqlite3")
            exam_id = create_exam(connection, "Biology")

            set_exam_provider(connection, exam_id, "gemini", "gemini-1.5-pro")

            exam = get_exam(connection, exam_id)
            self.assertEqual((exam["provider"], exam["model"]), ("gemini", "gemini-1.5-pro"))

    def test_adds_provider_columns_to_a_legacy_exams_table(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            connection.execute(
                "CREATE TABLE exams (exam_id TEXT PRIMARY KEY, name TEXT NOT NULL,"
                " created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )

            initialise_database(connection)

            set_exam_provider(connection, "default", "openai", "gpt-4o")
            self.assertEqual(get_exam(connection, "default")["provider"], "openai")


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


if __name__ == "__main__":
    unittest.main()
