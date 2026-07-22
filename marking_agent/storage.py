import csv
import json

from .config import CSV_FIELDNAMES


def load_text_file(path, description):
    if not path.exists():
        raise FileNotFoundError(f"{description} file not found: {path}")
    return path.read_text(encoding="utf-8")


def load_mark_scheme(path):
    return load_text_file(path, "Mark scheme")


def build_csv_row(student_id, question_id, evaluation, action, final_score, notes, exam_id="", exam_name=""):
    return {
        "Exam ID": exam_id,
        "Exam Name": exam_name,
        "Student ID": student_id,
        "Question ID": question_id,
        "Provisional AI Output": json.dumps(evaluation, ensure_ascii=False, sort_keys=True),
        "Human Action": action,
        "Final Score": final_score,
        "Notes": notes,
    }


def record_to_csv_row(record):
    return {
        "Exam ID": record.get("exam_id", ""),
        "Exam Name": record.get("exam_name", ""),
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
