import json
import unittest

from marking_agent.analytics import (
    hardest_questions,
    question_statistics,
    student_totals,
    topic_statistics,
)


def record(question_id, student_id, topic, final_score, total):
    return {
        "question_id": question_id,
        "student_id": student_id,
        "topic": topic,
        "final_score": str(final_score),
        "provisional_ai_output": json.dumps({"total_marks_available": total}),
    }


SAMPLE = [
    record("Q1", "A", "Photosynthesis", 2, 2),
    record("Q1", "B", "Photosynthesis", 1, 2),
    record("Q2", "A", "Enzymes", 0, 2),
    record("Q2", "B", "Enzymes", 1, 2),
]


class QuestionStatsTests(unittest.TestCase):
    def test_average_percent_per_question(self):
        stats = {stat["question_id"]: stat for stat in question_statistics(SAMPLE)}

        self.assertEqual(stats["Q1"]["average_percent"], 75.0)
        self.assertEqual(stats["Q1"]["count"], 2)
        self.assertEqual(stats["Q2"]["average_percent"], 25.0)


class TopicStatsTests(unittest.TestCase):
    def test_groups_by_topic(self):
        stats = {stat["topic"]: stat for stat in topic_statistics(SAMPLE)}

        self.assertEqual(stats["Photosynthesis"]["average_percent"], 75.0)
        self.assertEqual(stats["Enzymes"]["average_percent"], 25.0)

    def test_untagged_when_topic_missing(self):
        stats = topic_statistics([record("Q1", "A", "", 1, 2)])

        self.assertEqual(stats[0]["topic"], "Untagged")


class StudentTotalsTests(unittest.TestCase):
    def test_totals_and_percent_per_student(self):
        stats = {stat["student_id"]: stat for stat in student_totals(SAMPLE)}

        self.assertEqual(stats["A"]["awarded"], 2.0)
        self.assertEqual(stats["A"]["available"], 4.0)
        self.assertEqual(stats["A"]["percent"], 50.0)


class HardestQuestionsTests(unittest.TestCase):
    def test_orders_by_lowest_average_first(self):
        hardest = hardest_questions(question_statistics(SAMPLE))

        self.assertEqual([stat["question_id"] for stat in hardest], ["Q2", "Q1"])

    def test_handles_zero_available_marks(self):
        stats = question_statistics([record("Q1", "A", "", 0, 0)])

        self.assertEqual(stats[0]["average_percent"], 0.0)


if __name__ == "__main__":
    unittest.main()
