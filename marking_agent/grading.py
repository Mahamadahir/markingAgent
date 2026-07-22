import json
from decimal import Decimal, InvalidOperation


GRADER_PROMPT = """You are a precise, objective academic grading assistant.

Evaluate one student response against the provided mark scheme snippet only. The response may be typed text or handwritten PDF page images.
Do not award marks for external knowledge or alternative correct answers unless the mark scheme explicitly permits them.
Flag assertions, methodologies, or terminology that deviate from or contradict the mark scheme.
Your evaluation is provisional and will be reviewed by a human marker.
Include a confidence between 0.0 and 1.0 for how certain you are of the proposed marks: low confidence for illegible handwriting, ambiguous answers, or a mark scheme that does not clearly cover the response.
Return only JSON matching the requested schema."""


LOW_CONFIDENCE_THRESHOLD = 0.6
CONSENSUS_TOLERANCE = Decimal("0.5")


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
            "confidence": {"type": "number"},
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
            "confidence",
            "criteria_breakdown",
        ],
    },
}


def build_dispatch_payload(student_id, question_id, student_answer, mark_scheme_snippet):
    return f"""Student ID: {student_id}
Question ID: {question_id}

MARK SCHEME SNIPPET:
{mark_scheme_snippet}

STUDENT RESPONSE:
{student_answer}"""


def grade_text_response(provider, student_id, question_id, student_answer, mark_scheme_snippet):
    user_text = build_dispatch_payload(student_id, question_id, student_answer, mark_scheme_snippet)
    content = provider.complete_json(GRADER_PROMPT, user_text, GRADING_RESPONSE_SCHEMA)
    return parse_grading_response(content, student_id, question_id)


def build_pdf_dispatch_text(student_id, question_id, mark_scheme_snippet):
    return f"""Student ID: {student_id}
Question ID: {question_id}

MARK SCHEME SNIPPET:
{mark_scheme_snippet}

STUDENT RESPONSE:
The student's handwritten response is attached as page images from their submitted PDF. Read the handwriting directly from the images. If a page or answer is illegible, say so in the evidence and avoid awarding unsupported marks."""


def grade_pdf_images(provider, student_id, question_id, image_urls, mark_scheme_snippet):
    user_text = build_pdf_dispatch_text(student_id, question_id, mark_scheme_snippet)
    content = provider.complete_json(GRADER_PROMPT, user_text, GRADING_RESPONSE_SCHEMA, image_urls)
    return parse_grading_response(content, student_id, question_id)


def parse_grading_response(content, student_id, question_id):
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
    validate_confidence(evaluation.get("confidence"))


def validate_confidence(value):
    confidence = decimal_from_value(value)
    if confidence < 0 or confidence > 1:
        raise ValueError("Confidence must be between 0 and 1.")


def confidence_value(evaluation):
    value = evaluation.get("confidence")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_low_confidence(evaluation):
    confidence = confidence_value(evaluation)
    return confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD


def build_consensus(evaluations, models):
    proposals = [decimal_from_value(evaluation["proposed_marks_awarded"]) for evaluation in evaluations]
    spread = max(proposals) - min(proposals)
    return {
        "agreement": spread <= CONSENSUS_TOLERANCE,
        "spread": format_decimal(spread),
        "models": [
            {
                "model": model,
                "proposed_marks_awarded": evaluation["proposed_marks_awarded"],
                "confidence": evaluation.get("confidence"),
            }
            for model, evaluation in zip(models, evaluations)
        ],
    }


def consensus_disagreement(evaluation):
    consensus = evaluation.get("consensus")
    return bool(consensus) and not consensus.get("agreement", True)


def needs_review(evaluation):
    return is_low_confidence(evaluation) or consensus_disagreement(evaluation)


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


def confidence_line(evaluation):
    confidence = confidence_value(evaluation)
    if confidence is None:
        return "Confidence: not reported"
    flag = "  [LOW - REVIEW]" if is_low_confidence(evaluation) else ""
    return f"Confidence: {confidence:.0%}{flag}"


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
        confidence_line(evaluation),
        "",
        "Criteria breakdown:",
    ]

    for item in evaluation["criteria_breakdown"]:
        status = "Awarded" if item["awarded"] else "Not awarded"
        lines.append(f"- {item['criterion']}: {status} - {item['evidence']}")

    lines.extend(consensus_lines(evaluation))
    return "\n".join(lines)


def consensus_lines(evaluation):
    consensus = evaluation.get("consensus")
    if not consensus:
        return []
    verdict = "AGREEMENT" if consensus["agreement"] else "DISAGREEMENT - REVIEW"
    lines = ["", f"Multi-model {verdict} (spread {consensus['spread']} marks):"]
    for model in consensus["models"]:
        confidence = model.get("confidence")
        confidence_text = "n/a" if confidence is None else f"{float(confidence):.0%}"
        lines.append(f"- {model['model']}: {model['proposed_marks_awarded']} marks (confidence {confidence_text})")
    return lines
