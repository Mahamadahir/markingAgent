import json
from decimal import Decimal

from .grading import decimal_from_value


UNTAGGED_TOPIC = "Untagged"


def record_marks(record):
    evaluation = json.loads(record["provisional_ai_output"])
    awarded = decimal_from_value(record["final_score"]) if record.get("final_score") else Decimal(0)
    available = decimal_from_value(evaluation.get("total_marks_available", 0))
    return awarded, available


def percent(awarded, available):
    if available == 0:
        return 0.0
    return round(float(awarded / available * 100), 1)


def question_statistics(records):
    groups = {}
    for record in records:
        awarded, available = record_marks(record)
        group = groups.setdefault(
            record["question_id"],
            {"question_id": record["question_id"], "topic": record.get("topic") or "", "awarded": Decimal(0), "available": Decimal(0), "count": 0},
        )
        group["awarded"] += awarded
        group["available"] += available
        group["count"] += 1
    return [
        {
            "question_id": group["question_id"],
            "topic": group["topic"],
            "count": group["count"],
            "average_percent": percent(group["awarded"], group["available"]),
        }
        for group in groups.values()
    ]


def topic_statistics(records):
    groups = {}
    for record in records:
        topic = (record.get("topic") or "").strip() or UNTAGGED_TOPIC
        awarded, available = record_marks(record)
        group = groups.setdefault(topic, {"topic": topic, "awarded": Decimal(0), "available": Decimal(0), "count": 0})
        group["awarded"] += awarded
        group["available"] += available
        group["count"] += 1
    return [
        {"topic": group["topic"], "count": group["count"], "average_percent": percent(group["awarded"], group["available"])}
        for group in groups.values()
    ]


def student_totals(records):
    groups = {}
    for record in records:
        awarded, available = record_marks(record)
        group = groups.setdefault(
            record["student_id"],
            {"student_id": record["student_id"], "awarded": Decimal(0), "available": Decimal(0), "count": 0},
        )
        group["awarded"] += awarded
        group["available"] += available
        group["count"] += 1
    return [
        {
            "student_id": group["student_id"],
            "questions": group["count"],
            "awarded": float(group["awarded"]),
            "available": float(group["available"]),
            "percent": percent(group["awarded"], group["available"]),
        }
        for group in groups.values()
    ]


def hardest_questions(question_stats, limit=5):
    return sorted(question_stats, key=lambda stat: stat["average_percent"])[:limit]
