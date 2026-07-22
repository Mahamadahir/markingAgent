import tempfile
import unittest
from pathlib import Path

from marking_agent.state import (
    AI_GENERATED,
    APPROVED,
    create_exam,
    evaluation_from_record,
    get_record,
    is_final_record,
    save_human_decision,
    save_provisional_evaluation,
)
from tests.helpers import create_test_database, sample_evaluation


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
