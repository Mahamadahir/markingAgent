from pathlib import Path

from .config import DEFAULT_DB_PATH, DEFAULT_EXAM_NAME, DEFAULT_OUTPUT_PATH
from .grading import (
    build_consensus,
    confidence_value,
    decimal_from_value,
    format_decimal,
    grade_pdf_images,
    grade_text_response,
    needs_review,
    validate_score_range,
)
from .page_mapping import ScriptPages
from .providers import build_provider
from .mark_scheme import extract_mark_scheme_snippet, list_question_ids
from .pdf_submissions import (
    FULL_SCRIPT_QUESTION_ID,
    expand_submissions_by_question,
    load_pdf_submissions,
)
from .pdf_extract import extract_pdf_text, write_extracted_text
from .state import (
    APPROVED,
    OVERRIDDEN,
    connect_database,
    ensure_exam,
    evaluation_from_record,
    get_exam,
    get_record,
    initialise_database,
    iter_records,
    list_exams,
    get_question_topics,
    save_human_decision,
    save_provisional_evaluation,
    set_exam_provider,
    set_question_topics,
)
from .topics import extract_question_topics
from .storage import export_records_to_csv, load_mark_scheme


class AppService:
    def __init__(self, db_path=DEFAULT_DB_PATH, output_path=DEFAULT_OUTPUT_PATH, exam_id=None, exam_name=DEFAULT_EXAM_NAME):
        self.db_path = Path(db_path)
        self.output_path = Path(output_path)
        self.connection = connect_database(self.db_path)
        initialise_database(self.connection)
        self.exam_id = ensure_exam(self.connection, exam_id=exam_id, name=exam_name)
        self._provider = None
        self._provider_settings = None
        self._resolver = None
        self._resolver_key = None

    def close(self):
        self.connection.close()

    def exams(self):
        return list_exams(self.connection)

    def set_exam(self, exam_id=None, exam_name=None, **metadata):
        self.exam_id = ensure_exam(self.connection, exam_id=exam_id, name=exam_name or DEFAULT_EXAM_NAME, **metadata)
        return self.exam_id

    def extract_pdf(self, pdf_path, output_path, ocr_mode="never"):
        pages = extract_pdf_text(Path(pdf_path), ocr_mode=ocr_mode)
        write_extracted_text(pages, Path(output_path))
        return pages

    def _question_ids(self, mark_scheme_path):
        if not mark_scheme_path or not Path(mark_scheme_path).exists():
            return []
        return list_question_ids(load_mark_scheme(Path(mark_scheme_path)))

    def load_exam_items(self, submissions_path, mark_scheme_path=None):
        submissions = load_pdf_submissions(Path(submissions_path))
        submissions = expand_submissions_by_question(submissions, self._question_ids(mark_scheme_path))
        items = []
        for submission in submissions:
            student_id = submission["student_id"]
            question_id = submission["question_id"]
            record = get_record(self.connection, self.exam_id, student_id, question_id)
            status = record["status"] if record else "PENDING"
            evaluation = evaluation_from_record(record) if record else None
            items.append(
                {
                    "exam_id": self.exam_id,
                    "student_id": student_id,
                    "question_id": question_id,
                    "pdf_path": submission["pdf_path"],
                    "status": status,
                    "confidence": confidence_value(evaluation) if evaluation else None,
                    "flagged": bool(evaluation) and needs_review(evaluation),
                }
            )
        items.sort(key=review_sort_key)
        return items

    def get_saved_evaluation(self, student_id, question_id):
        record = get_record(self.connection, self.exam_id, student_id, question_id)
        if not record:
            return None
        return evaluation_from_record(record)

    def provider_for(self, settings):
        if self._provider is None or settings != self._provider_settings:
            self._provider = build_provider(settings)
            self._provider_settings = settings
            self._remember_provider(settings)
        return self._provider

    def _remember_provider(self, settings):
        provider = getattr(settings, "provider", "")
        if provider:
            set_exam_provider(self.connection, self.exam_id, provider, getattr(settings, "model", ""))

    def stored_provider(self):
        exam = get_exam(self.connection, self.exam_id)
        if not exam or not exam.get("provider"):
            return None
        return {"provider": exam["provider"], "model": exam.get("model", "")}

    def resolver_for(self, settings, question_ids):
        key = (settings, tuple(question_ids))
        if self._resolver is None or key != self._resolver_key:
            self._resolver = ScriptPages(self.provider_for(settings), question_ids)
            self._resolver_key = key
        return self._resolver

    def list_models(self, settings):
        return build_provider(settings).list_models()

    def extract_topics(self, settings, mark_scheme_path):
        mark_scheme = load_mark_scheme(Path(mark_scheme_path))
        question_ids = list_question_ids(mark_scheme)
        if not question_ids:
            return {}
        topics = extract_question_topics(build_provider(settings), mark_scheme, question_ids)
        set_question_topics(self.connection, self.exam_id, topics)
        return topics

    def question_topics(self):
        return get_question_topics(self.connection, self.exam_id)

    def grade_item(self, settings, mark_scheme_path, item, force=False):
        return self.grade_item_with_models([settings], mark_scheme_path, item, force=force)

    def grade_item_with_models(self, settings_list, mark_scheme_path, item, force=False):
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

        primary = settings_list[0]
        self._remember_provider(primary)

        if "pdf_path" in item:
            resolver = self.resolver_for(primary, list_question_ids(mark_scheme))
            image_urls = resolver.pages_for(item["pdf_path"], question_id)
            evaluations = [
                grade_pdf_images(build_provider(settings), student_id, question_id, image_urls, snippet)
                for settings in settings_list
            ]
        else:
            evaluations = [
                grade_text_response(build_provider(settings), student_id, question_id, item["answer"], snippet)
                for settings in settings_list
            ]

        evaluation = evaluations[0]
        if len(settings_list) > 1:
            evaluation = dict(evaluation)
            evaluation["consensus"] = build_consensus(evaluations, [settings.model for settings in settings_list])

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


def review_sort_key(item):
    is_final = item["status"] in {APPROVED, OVERRIDDEN}
    confidence = item.get("confidence")
    return (is_final, not item.get("flagged", False), confidence if confidence is not None else 2.0)


def normalise_action(action):
    upper_action = action.strip().upper()
    if upper_action == "APPROVE":
        return APPROVED
    if upper_action == "OVERRIDE":
        return OVERRIDDEN
    if upper_action in {APPROVED, OVERRIDDEN}:
        return upper_action
    raise ValueError("Action must be APPROVE or OVERRIDE.")
