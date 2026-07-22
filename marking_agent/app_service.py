from pathlib import Path

from .config import DEFAULT_DB_PATH, DEFAULT_EXAM_NAME, DEFAULT_OUTPUT_PATH, provider_settings
from .grading import (
    decimal_from_value,
    format_decimal,
    grade_pdf_response,
    grade_text_response,
    validate_score_range,
)
from .providers import build_provider
from .mark_scheme import extract_mark_scheme_snippet
from .pdf_submissions import FULL_SCRIPT_QUESTION_ID, load_pdf_submissions
from .pdf_extract import extract_pdf_text, write_extracted_text
from .state import (
    APPROVED,
    OVERRIDDEN,
    connect_database,
    ensure_exam,
    evaluation_from_record,
    get_record,
    initialise_database,
    iter_records,
    list_exams,
    save_human_decision,
    save_provisional_evaluation,
)
from .storage import export_records_to_csv, load_mark_scheme


class AppService:
    def __init__(self, db_path=DEFAULT_DB_PATH, output_path=DEFAULT_OUTPUT_PATH, exam_id=None, exam_name=DEFAULT_EXAM_NAME):
        self.db_path = Path(db_path)
        self.output_path = Path(output_path)
        self.connection = connect_database(self.db_path)
        initialise_database(self.connection)
        self.exam_id = ensure_exam(self.connection, exam_id=exam_id, name=exam_name)
        self._provider = None

    def close(self):
        self.connection.close()

    def exams(self):
        return list_exams(self.connection)

    def set_exam(self, exam_id=None, exam_name=None, **metadata):
        self.exam_id = ensure_exam(self.connection, exam_id=exam_id, name=exam_name or DEFAULT_EXAM_NAME, **metadata)
        return self.exam_id

    def extract_pdf(self, pdf_path, output_path):
        pages = extract_pdf_text(Path(pdf_path))
        write_extracted_text(pages, Path(output_path))
        return pages

    def load_exam_items(self, submissions_path):
        submissions = load_pdf_submissions(Path(submissions_path))
        items = []
        for submission in submissions:
            student_id = submission["student_id"]
            question_id = submission["question_id"]
            record = get_record(self.connection, self.exam_id, student_id, question_id)
            status = record["status"] if record else "PENDING"
            items.append(
                {
                    "exam_id": self.exam_id,
                    "student_id": student_id,
                    "question_id": question_id,
                    "pdf_path": submission["pdf_path"],
                    "status": status,
                }
            )
        return items

    def get_saved_evaluation(self, student_id, question_id):
        record = get_record(self.connection, self.exam_id, student_id, question_id)
        if not record:
            return None
        return evaluation_from_record(record)

    def grade_item(self, model, mark_scheme_path, item, force=False):
        student_id = item["student_id"]
        question_id = item["question_id"]
        record = get_record(self.connection, self.exam_id, student_id, question_id)
        if record and not force:
            return evaluation_from_record(record)

        mark_scheme = load_mark_scheme(Path(mark_scheme_path))
        if question_id == FULL_SCRIPT_QUESTION_ID:
            snippet = mark_scheme
        else:
            snippet = extract_mark_scheme_snippet(mark_scheme, question_id)

        if self._provider is None:
            self._provider = build_provider(provider_settings(model))

        if "pdf_path" in item:
            evaluation = grade_pdf_response(
                self._provider,
                student_id,
                question_id,
                item["pdf_path"],
                snippet,
            )
        else:
            evaluation = grade_text_response(
                self._provider,
                student_id,
                question_id,
                item["answer"],
                snippet,
            )
        save_provisional_evaluation(self.connection, self.exam_id, student_id, question_id, evaluation, force=force)
        return evaluation

    def save_decision(self, student_id, question_id, evaluation, action, final_score, notes):
        total_marks = decimal_from_value(evaluation["total_marks_available"])
        score = decimal_from_value(final_score)
        validate_score_range(score, total_marks)
        normalised_score = format_decimal(score)
        save_human_decision(
            self.connection,
            self.exam_id,
            student_id,
            question_id,
            evaluation,
            action,
            normalised_score,
            notes,
        )
        self.export_csv(self.output_path)
        return normalised_score

    def export_csv(self, output_path=None, exam_id=None):
        path = Path(output_path) if output_path else self.output_path
        records = iter_records(self.connection, exam_id=exam_id or self.exam_id, final_only=True)
        export_records_to_csv(records, path)
        return len(records)

    def records(self, final_only=False, exam_id=None):
        return iter_records(self.connection, exam_id=exam_id or self.exam_id, final_only=final_only)


def normalise_action(action):
    upper_action = action.strip().upper()
    if upper_action == "APPROVE":
        return APPROVED
    if upper_action == "OVERRIDE":
        return OVERRIDDEN
    if upper_action in {APPROVED, OVERRIDDEN}:
        return upper_action
    raise ValueError("Action must be APPROVE or OVERRIDE.")
