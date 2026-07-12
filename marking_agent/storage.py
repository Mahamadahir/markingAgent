import csv
import json

from .config import CSV_FIELDNAMES


def load_text_file(path, description):
    if not path.exists():
        raise FileNotFoundError(f"{description} file not found: {path}")
    return path.read_text(encoding="utf-8")


def load_mark_scheme(path):
    return load_text_file(path, "Mark scheme")


def load_student_data(path):
    if not path.exists():
        raise FileNotFoundError(f"Student exam file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Student exam file is not valid JSON: {error}") from error

    validate_student_data(data)
    return data


def validate_student_data(data):
    if not isinstance(data, list):
        raise ValueError("Student exam file must contain a JSON array.")

    for index, entry in enumerate(data, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Student entry {index} must be an object.")
        if not entry.get("student_id"):
            raise ValueError(f"Student entry {index} is missing student_id.")
        if not isinstance(entry.get("exam_responses"), dict):
            raise ValueError(f"Student entry {index} must include exam_responses object.")


def build_csv_row(student_id, question_id, evaluation, action, final_score, notes):
    return {
        "Student ID": student_id,
        "Question ID": question_id,
        "Provisional AI Output": json.dumps(evaluation, ensure_ascii=False, sort_keys=True),
        "Human Action": action,
        "Final Score": final_score,
        "Notes": notes,
    }


def record_to_csv_row(record):
    return {
        "Student ID": record["student_id"],
        "Question ID": record["question_id"],
        "Provisional AI Output": record["provisional_ai_output"],
        "Human Action": record["human_action"] or "",
        "Final Score": record["final_score"] or "",
        "Notes": record["notes"] or "",
    }


def export_records_to_csv(records, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for record in records:
            writer.writerow(record_to_csv_row(record))
