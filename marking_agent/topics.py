import json

from .mark_scheme import normalise_question_id


TOPIC_PROMPT = """You label exam questions with the topic each one assesses.

Read the mark scheme and, for every question ID provided, give a short topic label of two to four words naming the subject area the question covers, for example "Photosynthesis" or "Quadratic equations".
Use the mark scheme wording where it names a topic. Use only the question IDs provided.
Return only JSON matching the requested schema."""


TOPIC_SCHEMA = {
    "name": "question_topics",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "topics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "question_id": {"type": "string"},
                        "topic": {"type": "string"},
                    },
                    "required": ["question_id", "topic"],
                },
            }
        },
        "required": ["topics"],
    },
}


def build_topic_text(mark_scheme, question_ids):
    joined = ", ".join(question_ids)
    return f"Question IDs: {joined}\n\nMARK SCHEME:\n{mark_scheme}"


def extract_question_topics(provider, mark_scheme, question_ids):
    user_text = build_topic_text(mark_scheme, question_ids)
    content = provider.complete_json(TOPIC_PROMPT, user_text, TOPIC_SCHEMA)
    return parse_topics(content, question_ids)


def parse_topics(content, question_ids):
    known = set(question_ids)
    data = json.loads(content)
    topics = {}
    for entry in data.get("topics", []):
        question_id = normalise_question_id(entry.get("question_id", ""))
        topic = entry.get("topic", "").strip()
        if question_id in known and topic:
            topics[question_id] = topic
    return topics
