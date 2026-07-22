import contextlib
import io
import json

from marking_agent.pdf_submissions import FULL_SCRIPT_QUESTION_ID
from marking_agent.state import connect_database, initialise_database


def sample_evaluation():
    return {
        "student_id": "STUDENT_001",
        "question_id": "Q1",
        "deviation_detected": False,
        "deviation_notes": "",
        "total_marks_available": 2,
        "proposed_marks_awarded": 2,
        "confidence": 0.9,
        "criteria_breakdown": [],
    }


def full_script_evaluation(student_id, marks=2):
    evaluation = sample_evaluation()
    evaluation["student_id"] = student_id
    evaluation["question_id"] = FULL_SCRIPT_QUESTION_ID
    evaluation["proposed_marks_awarded"] = marks
    return evaluation


def create_test_database(path):
    connection = connect_database(path)
    initialise_database(connection)
    return connection


def write_submissions(directory):
    (directory / "STUDENT_001.pdf").write_bytes(b"pdf")
    (directory / "STUDENT_002.pdf").write_bytes(b"pdf")


class FakeProvider:
    def __init__(self, evaluation):
        self._payload = json.dumps(evaluation)
        self.calls = []

    def complete_json(self, system_prompt, user_text, schema, image_data_urls=None):
        self.calls.append((system_prompt, user_text, schema, image_data_urls))
        return self._payload


class QuietStdoutMixin:
    def setUp(self):
        redirect = contextlib.redirect_stdout(io.StringIO())
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)
