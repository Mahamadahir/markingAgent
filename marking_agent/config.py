import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MODEL = "gpt-4o"
DEFAULT_MARK_SCHEME_PATH = Path("mark_scheme.txt")
DEFAULT_SUBMISSIONS_PATH = Path("data/input/submissions")
DEFAULT_OUTPUT_PATH = Path("data/output/grading_output.csv")
DEFAULT_DB_PATH = Path("data/output/grading_state.sqlite3")
DEFAULT_EXAM_NAME = "Default Exam"

DEFAULT_MODEL_ENV = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)

DEFAULT_PROVIDER = os.environ.get("GRADING_PROVIDER", "openai")
DEFAULT_AZURE_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
DEFAULT_AZURE_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")


@dataclass
class ProviderSettings:
    provider: str
    model: str
    azure_endpoint: str = ""
    azure_api_version: str = ""


def provider_settings(model, provider=None, azure_endpoint=None, azure_api_version=None):
    return ProviderSettings(
        provider=provider or DEFAULT_PROVIDER,
        model=model,
        azure_endpoint=DEFAULT_AZURE_ENDPOINT if azure_endpoint is None else azure_endpoint,
        azure_api_version=DEFAULT_AZURE_API_VERSION if azure_api_version is None else azure_api_version,
    )

CSV_FIELDNAMES = [
    "Exam ID",
    "Exam Name",
    "Student ID",
    "Question ID",
    "Provisional AI Output",
    "Human Action",
    "Final Score",
    "Notes",
]
