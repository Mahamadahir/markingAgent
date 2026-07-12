import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import main


class MarkSchemeTests(unittest.TestCase):
    def test_extracts_matching_question_section(self):
        mark_scheme = "# Q1\nOne\n\n# Q2\nTwo\n\n# Q3\nThree"

        snippet = main.extract_mark_scheme_snippet(mark_scheme, "Q2")

        self.assertEqual(snippet, "# Q2\nTwo")

    def test_accepts_question_word_heading(self):
        mark_scheme = "Question 1\nOne\n\nQuestion 2\nTwo"

        snippet = main.extract_mark_scheme_snippet(mark_scheme, "Q1")

        self.assertEqual(snippet, "Question 1\nOne")

    def test_falls_back_to_full_mark_scheme_when_no_heading_matches(self):
        mark_scheme = "General marking notes"

        snippet = main.extract_mark_scheme_snippet(mark_scheme, "Q9")

        self.assertEqual(snippet, mark_scheme)


class ValidationTests(unittest.TestCase):
    def test_score_cannot_exceed_total_marks(self):
        with self.assertRaises(ValueError):
            main.validate_score_range(Decimal("4"), Decimal("3"))

    def test_validates_model_result_identity(self):
        evaluation = {
            "student_id": "STUDENT_001",
            "question_id": "Q1",
            "total_marks_available": 2,
            "proposed_marks_awarded": 1,
        }

        main.validate_evaluation(evaluation, "STUDENT_001", "Q1")

    def test_rejects_mismatched_model_result_identity(self):
        evaluation = {
            "student_id": "STUDENT_002",
            "question_id": "Q1",
            "total_marks_available": 2,
            "proposed_marks_awarded": 1,
        }

        with self.assertRaises(ValueError):
            main.validate_evaluation(evaluation, "STUDENT_001", "Q1")


class CsvTests(unittest.TestCase):
    def test_load_completed_records_returns_existing_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "grading_output.csv"
            with output_path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=main.CSV_FIELDNAMES)
                writer.writeheader()
                writer.writerow(
                    {
                        "Student ID": "STUDENT_001",
                        "Question ID": "Q1",
                        "Provisional AI Output": "{}",
                        "Human Action": "APPROVE",
                        "Final Score": "2",
                        "Notes": "Approved",
                    }
                )

            completed_records = main.load_completed_records(output_path)

            self.assertEqual(completed_records, {("STUDENT_001", "Q1")})

    def test_build_csv_row_serialises_structured_evaluation(self):
        evaluation = {
            "student_id": "STUDENT_001",
            "question_id": "Q1",
            "deviation_detected": False,
            "deviation_notes": "",
            "total_marks_available": 2,
            "proposed_marks_awarded": 2,
            "criteria_breakdown": [],
        }

        row = main.build_csv_row("STUDENT_001", "Q1", evaluation, "APPROVE", "2", "Approved")

        self.assertEqual(json.loads(row["Provisional AI Output"]), evaluation)


if __name__ == "__main__":
    unittest.main()
