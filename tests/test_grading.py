import unittest
from decimal import Decimal

from marking_agent.grading import validate_evaluation, validate_score_range


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


if __name__ == "__main__":
    unittest.main()
