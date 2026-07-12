import os
from pathlib import Path


DEFAULT_MODEL = "gpt-4o"
DEFAULT_MARK_SCHEME_PATH = Path("mark_scheme.txt")
DEFAULT_STUDENTS_PATH = Path("students_exams.json")
DEFAULT_OUTPUT_PATH = Path("data/output/grading_output.csv")
DEFAULT_DB_PATH = Path("data/output/grading_state.sqlite3")

DEFAULT_MODEL_ENV = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)

CSV_FIELDNAMES = [
    "Student ID",
    "Question ID",
    "Provisional AI Output",
    "Human Action",
    "Final Score",
    "Notes",
]
