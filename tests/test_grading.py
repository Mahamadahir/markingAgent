import unittest
from decimal import Decimal

from marking_agent.grading import (
    build_consensus,
    consensus_disagreement,
    is_low_confidence,
    needs_review,
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


class ConsensusTests(unittest.TestCase):
    def test_agreement_within_tolerance(self):
        consensus = build_consensus(
            [evaluation(proposed_marks_awarded=2), evaluation(proposed_marks_awarded=2)],
            ["gpt-4o", "gpt-4o-mini"],
        )

        self.assertTrue(consensus["agreement"])
        self.assertEqual([m["model"] for m in consensus["models"]], ["gpt-4o", "gpt-4o-mini"])

    def test_disagreement_when_marks_differ(self):
        consensus = build_consensus(
            [evaluation(proposed_marks_awarded=2), evaluation(proposed_marks_awarded=0)],
            ["gpt-4o", "gpt-4o-mini"],
        )

        self.assertFalse(consensus["agreement"])
        self.assertTrue(consensus_disagreement({"consensus": consensus}))

    def test_needs_review_covers_disagreement_and_low_confidence(self):
        self.assertTrue(needs_review(evaluation(confidence=0.2)))
        self.assertTrue(needs_review({"consensus": {"agreement": False}}))
        self.assertFalse(needs_review(evaluation(confidence=0.95)))


if __name__ == "__main__":
    unittest.main()
