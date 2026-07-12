import re


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
