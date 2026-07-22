import argparse
import sys
from pathlib import Path

from .config import (
    DEFAULT_DB_PATH,
    DEFAULT_EXAM_NAME,
    DEFAULT_MARK_SCHEME_PATH,
    DEFAULT_MODEL_ENV,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_PROVIDER,
    DEFAULT_SUBMISSIONS_PATH,
    PROVIDER_CHOICES,
    provider_settings,
)
from .grading import (
    decimal_from_value,
    format_decimal,
    grade_pdf_response,
    render_evaluation,
    validate_score_range,
)
from .providers import build_provider
from .mark_scheme import extract_mark_scheme_snippet, list_question_ids
from .pdf_extract import extract_pdf_text, write_extracted_text
from .pdf_submissions import (
    FULL_SCRIPT_QUESTION_ID,
    expand_submissions_by_question,
    load_pdf_submissions,
)
from .state import (
    APPROVED,
    OVERRIDDEN,
    connect_database,
    ensure_exam,
    evaluation_from_record,
    get_record,
    initialise_database,
    is_final_record,
    iter_records,
    list_exams,
    save_human_decision,
    save_provisional_evaluation,
)
from .storage import export_records_to_csv, load_mark_scheme


def parse_args():
    parser = argparse.ArgumentParser(description="Human-reviewed exam grading CLI.")
    subparsers = parser.add_subparsers(dest="command")

    grade_parser = subparsers.add_parser("grade", help="Run the human-reviewed grading flow.")
    add_grading_arguments(grade_parser)

    extract_parser = subparsers.add_parser("extract-pdf", help="Extract selectable text from a mark scheme PDF.")
    extract_parser.add_argument("pdf_path")
    extract_parser.add_argument("output_path")

    export_parser = subparsers.add_parser("export-csv", help="Export finalised grades from SQLite to CSV.")
    export_parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH))
    export_parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_PATH))
    export_parser.add_argument("--exam-id", type=str, default="")
    export_parser.add_argument("--all-exams", action="store_true")

    list_parser = subparsers.add_parser("list-exams", help="List exams in the SQLite state database.")
    list_parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH))

    add_grading_arguments(parser)
    return parser.parse_args()


def add_grading_arguments(parser):
    parser.add_argument("--exam-id", type=str, default="")
    parser.add_argument("--exam-name", type=str, default=DEFAULT_EXAM_NAME)
    parser.add_argument("--mark-scheme", type=str, default=str(DEFAULT_MARK_SCHEME_PATH))
    parser.add_argument("--submissions", type=str, default=str(DEFAULT_SUBMISSIONS_PATH))
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH))
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--model", default=DEFAULT_MODEL_ENV)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, choices=PROVIDER_CHOICES)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--azure-endpoint", default=None)
    parser.add_argument("--azure-api-version", default=None)
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Re-grade entries already present in the selected exam.",
    )


def prompt_action():
    while True:
        action = input("Enter decision ('APPROVE' or 'OVERRIDE'): ").strip().upper()
        if action == "APPROVE":
            return APPROVED
        if action == "OVERRIDE":
            return OVERRIDDEN
        print("Decision must be APPROVE or OVERRIDE.")


def prompt_score(prompt, total_marks, default=None):
    suffix = f" [{default}]" if default else ""
    while True:
        raw_value = input(f"{prompt}{suffix}: ").strip()
        if not raw_value and default:
            raw_value = default

        try:
            score = decimal_from_value(raw_value)
            validate_score_range(score, total_marks)
            return format_decimal(score)
        except ValueError as error:
            print(f"Invalid score: {error}")


def prompt_override_reason():
    while True:
        reason = input("Provide mandatory audit reason for override: ").strip()
        if reason:
            return reason
        print("Override reason is required.")


def get_or_create_evaluation(connection, exam_id, args, provider, submission, mark_scheme):
    student_id = submission["student_id"]
    question_id = submission["question_id"]
    existing_record = get_record(connection, exam_id, student_id, question_id)
    if existing_record and not args.no_resume:
        if is_final_record(existing_record):
            print(f"Skipping already finalised record: {student_id} | {question_id}")
            return None
        print(f"Resuming saved provisional evaluation: {student_id} | {question_id}")
        return evaluation_from_record(existing_record)

    mark_scheme_snippet = mark_scheme_for_question(mark_scheme, question_id)

    evaluation = grade_pdf_response(
        provider,
        student_id,
        question_id,
        submission["pdf_path"],
        mark_scheme_snippet,
    )
    save_provisional_evaluation(connection, exam_id, student_id, question_id, evaluation, force=args.no_resume)
    return evaluation


def mark_scheme_for_question(mark_scheme, question_id):
    if question_id == FULL_SCRIPT_QUESTION_ID:
        return mark_scheme

    snippet = extract_mark_scheme_snippet(mark_scheme, question_id)
    if snippet == mark_scheme.strip():
        print(f"Warning: no specific mark scheme snippet found for {question_id}.")
    return snippet


def export_finalised_records(connection, output_path, exam_id=None):
    records = iter_records(connection, exam_id=exam_id, final_only=True)
    export_records_to_csv(records, output_path)
    return len(records)


def grade_all(args):
    mark_scheme_path = Path(args.mark_scheme)
    submissions_path = Path(args.submissions)
    db_path = Path(args.db)
    output_path = Path(args.output)

    mark_scheme = load_mark_scheme(mark_scheme_path)
    submissions = load_pdf_submissions(submissions_path)
    submissions = expand_submissions_by_question(submissions, list_question_ids(mark_scheme))
    connection = connect_database(db_path)
    initialise_database(connection)
    exam_id = ensure_exam(
        connection,
        exam_id=args.exam_id or None,
        name=args.exam_name,
        mark_scheme_path=str(mark_scheme_path),
        students_path=str(submissions_path),
    )
    provider = build_provider(
        provider_settings(
            args.model,
            args.provider,
            api_key=args.api_key,
            azure_endpoint=args.azure_endpoint,
            azure_api_version=args.azure_api_version,
        )
    )

    try:
        print(f"Exam: {args.exam_name} ({exam_id})")
        for submission in submissions:
            student_id = submission["student_id"]
            question_id = submission["question_id"]
            print()
            print(f"Running evaluation: {student_id} | {question_id}")
            evaluation = get_or_create_evaluation(
                connection,
                exam_id,
                args,
                provider,
                submission,
                mark_scheme,
            )
            if evaluation is None:
                continue

            print()
            print(render_evaluation(evaluation))
            print()

            total_marks = decimal_from_value(evaluation["total_marks_available"])
            proposed_score = format_decimal(decimal_from_value(evaluation["proposed_marks_awarded"]))
            action = prompt_action()

            if action == APPROVED:
                final_score = prompt_score("Confirm numeric score to log", total_marks, proposed_score)
                notes = "Approved AI assessment."
            else:
                final_score = prompt_score("Input overridden numeric score", total_marks)
                notes = prompt_override_reason()

            save_human_decision(connection, exam_id, student_id, question_id, evaluation, action, final_score, notes)
            exported_count = export_finalised_records(connection, output_path, exam_id=exam_id)
            print(f"Recorded: {student_id} | {question_id}")
            print(f"Exported {exported_count} finalised record(s) to {output_path}")
    finally:
        connection.close()


def extract_pdf_command(args):
    pages = extract_pdf_text(Path(args.pdf_path))
    write_extracted_text(pages, Path(args.output_path))
    print(f"Extracted {len(pages)} page(s) to {args.output_path}")


def export_csv_command(args):
    connection = connect_database(Path(args.db))
    initialise_database(connection)
    try:
        exam_id = None if args.all_exams else args.exam_id or None
        exported_count = export_finalised_records(connection, Path(args.output), exam_id=exam_id)
    finally:
        connection.close()
    print(f"Exported {exported_count} finalised record(s) to {args.output}")


def list_exams_command(args):
    connection = connect_database(Path(args.db))
    initialise_database(connection)
    try:
        for exam in list_exams(connection):
            print(f"{exam['exam_id']}\t{exam['name']}")
    finally:
        connection.close()


def main():
    args = parse_args()
    command = args.command or "grade"

    try:
        if command == "extract-pdf":
            extract_pdf_command(args)
        elif command == "export-csv":
            export_csv_command(args)
        elif command == "list-exams":
            list_exams_command(args)
        else:
            grade_all(args)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0
