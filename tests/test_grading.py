import unittest
from decimal import Decimal

from marking_agent.grading import (
    is_low_confidence,
    validate_evaluation,
    validate_score_range,
)


def evaluation(**overrides):
    base = {
        "student_id": "STUDENT_001",
        "question_id": "Q1",
        "total_marks_available": 2,
        "proposed_marks_awarded": 1,
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


class ValidationTests(unittest.TestCase):
    def test_score_cannot_exceed_total_marks(self):
        with self.assertRaises(ValueError):
            validate_score_range(Decimal("4"), Decimal("3"))

    def test_validates_model_result_identity(self):
        validate_evaluation(evaluation(), "STUDENT_001", "Q1")

    def test_rejects_mismatched_model_result_identity(self):
        with self.assertRaises(ValueError):
            validate_evaluation(evaluation(student_id="STUDENT_002"), "STUDENT_001", "Q1")

    def test_rejects_confidence_out_of_range(self):
        with self.assertRaises(ValueError):
            validate_evaluation(evaluation(confidence=1.5), "STUDENT_001", "Q1")


class ConfidenceTests(unittest.TestCase):
    def test_flags_low_confidence(self):
        self.assertTrue(is_low_confidence(evaluation(confidence=0.3)))

    def test_does_not_flag_high_confidence(self):
        self.assertFalse(is_low_confidence(evaluation(confidence=0.9)))

    def test_missing_confidence_is_not_flagged(self):
        self.assertFalse(is_low_confidence({"student_id": "STUDENT_001"}))


if __name__ == "__main__":
    unittest.main()
