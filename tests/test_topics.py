import json
import tempfile
import unittest
from pathlib import Path

from marking_agent.state import get_question_topics, set_question_topics
from marking_agent.topics import extract_question_topics, parse_topics
from tests.helpers import create_test_database


class ParseTopicsTests(unittest.TestCase):
    def test_keeps_known_questions_and_normalises_ids(self):
        content = json.dumps(
            {
                "topics": [
                    {"question_id": "question 1", "topic": "Photosynthesis"},
                    {"question_id": "Q2", "topic": "Enzymes"},
                    {"question_id": "Q9", "topic": "Not in scheme"},
                ]
            }
        )

        topics = parse_topics(content, ["Q1", "Q2"])

        self.assertEqual(topics, {"Q1": "Photosynthesis", "Q2": "Enzymes"})

    def test_drops_empty_topics(self):
        content = json.dumps({"topics": [{"question_id": "Q1", "topic": "  "}]})

        self.assertEqual(parse_topics(content, ["Q1"]), {})


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, system_prompt, user_text, schema, image_data_urls=None):
        return self.payload


class ExtractTopicsTests(unittest.TestCase):
    def test_extracts_topics_via_provider(self):
        provider = FakeProvider(json.dumps({"topics": [{"question_id": "Q1", "topic": "Kinematics"}]}))

        topics = extract_question_topics(provider, "# Q1\nmarks", ["Q1"])

        self.assertEqual(topics, {"Q1": "Kinematics"})


class StoreTopicsTests(unittest.TestCase):
    def test_set_and_get_round_trip_and_upsert(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = create_test_database(Path(directory) / "state.sqlite3")

            set_question_topics(connection, "exam-1", {"Q1": "Photosynthesis", "Q2": "Enzymes"})
            set_question_topics(connection, "exam-1", {"Q1": "Cell respiration"})

            self.assertEqual(
                get_question_topics(connection, "exam-1"),
                {"Q1": "Cell respiration", "Q2": "Enzymes"},
            )


if __name__ == "__main__":
    unittest.main()
