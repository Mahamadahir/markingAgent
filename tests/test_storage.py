import csv
import json
import tempfile
import unittest
from pathlib import Path

from marking_agent.state import APPROVED, iter_records, save_human_decision
from marking_agent.storage import build_csv_row, export_records_to_csv
from tests.helpers import create_test_database, sample_evaluation


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


if __name__ == "__main__":
    unittest.main()
