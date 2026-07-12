import argparse
import csv
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path


DEFAULT_MODEL = "gpt-4o"
DEFAULT_MARK_SCHEME_PATH = Path("mark_scheme.txt")
DEFAULT_STUDENTS_PATH = Path("students_exams.json")
DEFAULT_OUTPUT_PATH = Path("grading_output.csv")

CSV_FIELDNAMES = [
    "Student ID",
    "Question ID",
    "Provisional AI Output",
    "Human Action",
    "Final Score",
    "Notes",
]


GRADER_PROMPT = """You are a precise, objective academic grading assistant.

Evaluate one student response against the provided mark scheme snippet only.
Do not award marks for external knowledge or alternative correct answers unless the mark scheme explicitly permits them.
Flag assertions, methodologies, or terminology that deviate from or contradict the mark scheme.
Your evaluation is provisional and will be reviewed by a human marker.
Return only JSON matching the requested schema."""


GRADING_RESPONSE_SCHEMA = {
    "name": "grading_evaluation",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "student_id": {"type": "string"},
            "question_id": {"type": "string"},
            "deviation_detected": {"type": "boolean"},
            "deviation_notes": {"type": "string"},
            "total_marks_available": {"type": "number"},
            "proposed_marks_awarded": {"type": "number"},
            "criteria_breakdown": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "criterion": {"type": "string"},
                        "awarded": {"type": "boolean"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["criterion", "awarded", "evidence"],
                },
            },
        },
        "required": [
            "student_id",
            "question_id",
            "deviation_detected",
            "deviation_notes",
            "total_marks_available",
            "proposed_marks_awarded",
            "criteria_breakdown",
        ],
    },
}


def parse_args():
    parser = argparse.ArgumentParser(description="Human-reviewed exam grading CLI.")
    parser.add_argument("--mark-scheme", type=Path, default=DEFAULT_MARK_SCHEME_PATH)
    parser.add_argument("--students", type=Path, default=DEFAULT_STUDENTS_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL))
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Re-grade entries already present in the output CSV.",
    )
    return parser.parse_args()


def load_mark_scheme(path):
    if not path.exists():
        raise FileNotFoundError(f"Mark scheme file not found: {path}")
    return path.read_text(encoding="utf-8")


def load_student_data(path):
    if not path.exists():
        raise FileNotFoundError(f"Student exam file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Student exam file is not valid JSON: {error}") from error

    if not isinstance(data, list):
        raise ValueError("Student exam file must contain a JSON array.")

    for index, entry in enumerate(data, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Student entry {index} must be an object.")
        if not entry.get("student_id"):
            raise ValueError(f"Student entry {index} is missing student_id.")
        if not isinstance(entry.get("exam_responses"), dict):
            raise ValueError(f"Student entry {index} must include exam_responses object.")

    return data


def normalise_question_id(value):
    compact = re.sub(r"[^a-zA-Z0-9]", "", value).upper()
    question_match = re.fullmatch(r"QUESTION(\d+[A-Z]?)", compact)
    if question_match:
        return f"Q{question_match.group(1)}"
    if compact.startswith("Q"):
        return compact
    if re.fullmatch(r"\d+[A-Z]?", compact):
        return f"Q{compact}"
    return compact


def question_heading_id(line):
    match = re.match(
        r"^\s*(?:#{1,6}\s*)?(?:(question)\s*)?(q?\d+[a-z]?)\b",
        line,
        re.IGNORECASE,
    )
    if not match:
        return None
    return normalise_question_id(match.group(2))


def extract_mark_scheme_snippet(mark_scheme, question_id):
    target_id = normalise_question_id(question_id)
    lines = mark_scheme.splitlines()
    headings = []

    for index, line in enumerate(lines):
        heading_id = question_heading_id(line)
        if heading_id:
            headings.append((index, heading_id))

    for heading_index, (start, heading_id) in enumerate(headings):
        if heading_id != target_id:
            continue
        end = headings[heading_index + 1][0] if heading_index + 1 < len(headings) else len(lines)
        return "\n".join(lines[start:end]).strip()

    return mark_scheme.strip()


def load_completed_records(path):
    if not path.exists():
        return set()

    with path.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        return {
            (row.get("Student ID", ""), row.get("Question ID", ""))
            for row in reader
            if row.get("Student ID") and row.get("Question ID")
        }


def create_openai_client():
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError(
            "The openai package is not installed. Run: pip install -r requirements.txt"
        ) from error

    return OpenAI()


def build_dispatch_payload(student_id, question_id, student_answer, mark_scheme_snippet):
    return f"""Student ID: {student_id}
Question ID: {question_id}

MARK SCHEME SNIPPET:
{mark_scheme_snippet}

STUDENT RESPONSE:
{student_answer}"""


def call_grading_agent(client, model, student_id, question_id, student_answer, mark_scheme_snippet):
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": GRADER_PROMPT},
            {
                "role": "user",
                "content": build_dispatch_payload(
                    student_id,
                    question_id,
                    student_answer,
                    mark_scheme_snippet,
                ),
            },
        ],
        response_format={"type": "json_schema", "json_schema": GRADING_RESPONSE_SCHEMA},
        temperature=0,
    )

    content = response.choices[0].message.content
    try:
        evaluation = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(f"Model returned invalid JSON: {content}") from error

    validate_evaluation(evaluation, student_id, question_id)
    return evaluation


def validate_evaluation(evaluation, student_id, question_id):
    if evaluation.get("student_id") != student_id:
        raise ValueError("Model response student_id does not match the dispatch.")
    if evaluation.get("question_id") != question_id:
        raise ValueError("Model response question_id does not match the dispatch.")

    total_marks = decimal_from_value(evaluation.get("total_marks_available"))
    proposed_marks = decimal_from_value(evaluation.get("proposed_marks_awarded"))
    validate_score_range(proposed_marks, total_marks)


def decimal_from_value(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as error:
        raise ValueError(f"Invalid numeric value: {value}") from error


def validate_score_range(score, total_marks):
    if score < 0:
        raise ValueError("Score cannot be negative.")
    if total_marks < 0:
        raise ValueError("Total marks cannot be negative.")
    if score > total_marks:
        raise ValueError("Score cannot exceed total marks available.")


def format_decimal(value):
    normalised = value.normalize()
    if normalised == normalised.to_integral():
        return str(normalised.quantize(Decimal(1)))
    return format(normalised, "f")


def render_evaluation(evaluation):
    deviation = "YES" if evaluation["deviation_detected"] else "NO"
    lines = [
        f"PROVISIONAL EVALUATION: {evaluation['question_id']} (Student: {evaluation['student_id']})",
        "",
        f"Deviation detected: {deviation}",
        f"Deviation notes: {evaluation['deviation_notes'] or 'None'}",
        "",
        f"Total marks available: {evaluation['total_marks_available']}",
        f"Proposed marks awarded: {evaluation['proposed_marks_awarded']}",
        "",
        "Criteria breakdown:",
    ]

    for item in evaluation["criteria_breakdown"]:
        status = "Awarded" if item["awarded"] else "Not awarded"
        lines.append(f"- {item['criterion']}: {status} - {item['evidence']}")

    return "\n".join(lines)


def prompt_action():
    while True:
        action = input("Enter decision ('APPROVE' or 'OVERRIDE'): ").strip().upper()
        if action in {"APPROVE", "OVERRIDE"}:
            return action
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


def append_to_csv(row_data, path):
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row_data)


def build_csv_row(student_id, question_id, evaluation, action, final_score, notes):
    return {
        "Student ID": student_id,
        "Question ID": question_id,
        "Provisional AI Output": json.dumps(evaluation, ensure_ascii=False, sort_keys=True),
        "Human Action": action,
        "Final Score": final_score,
        "Notes": notes,
    }


def grade_all(args):
    mark_scheme = load_mark_scheme(args.mark_scheme)
    student_data = load_student_data(args.students)
    completed_records = set() if args.no_resume else load_completed_records(args.output)
    client = create_openai_client()

    for student_entry in student_data:
        student_id = student_entry["student_id"]
        responses = student_entry["exam_responses"]

        for question_id, student_answer in responses.items():
            record_key = (student_id, question_id)
            if record_key in completed_records:
                print(f"Skipping already graded record: {student_id} | {question_id}")
                continue

            print(f"\nRunning evaluation: {student_id} | {question_id}")
            mark_scheme_snippet = extract_mark_scheme_snippet(mark_scheme, question_id)
            if mark_scheme_snippet == mark_scheme.strip():
                print(f"Warning: no specific mark scheme snippet found for {question_id}.")

            evaluation = call_grading_agent(
                client,
                args.model,
                student_id,
                question_id,
                student_answer,
                mark_scheme_snippet,
            )

            print()
            print(render_evaluation(evaluation))
            print()

            total_marks = decimal_from_value(evaluation["total_marks_available"])
            proposed_score = format_decimal(decimal_from_value(evaluation["proposed_marks_awarded"]))
            action = prompt_action()

            if action == "APPROVE":
                final_score = prompt_score("Confirm numeric score to log", total_marks, proposed_score)
                notes = "Approved AI assessment."
            else:
                final_score = prompt_score("Input overridden numeric score", total_marks)
                notes = prompt_override_reason()

            append_to_csv(
                build_csv_row(student_id, question_id, evaluation, action, final_score, notes),
                args.output,
            )
            completed_records.add(record_key)
            print(f"Recorded: {student_id} | {question_id}")


def main():
    try:
        grade_all(parse_args())
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
