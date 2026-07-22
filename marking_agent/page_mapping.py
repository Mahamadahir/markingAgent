import json

from .mark_scheme import normalise_question_id
from .pdf_submissions import render_pdf_pages_as_data_urls


CLASSIFIER_PROMPT = """You are labelling the pages of a scanned handwritten exam script.

Each attached image is one page, numbered from 1 in the order given.
For every page, decide which of the listed question IDs the student is answering on that page.
A page may continue a previous question, start a new one, or contain more than one question, so a page can map to zero, one, or several question IDs.
Use only the question IDs provided. Set confident to false when the page is blank, illegible, or you cannot tell which question it belongs to.
Return only JSON matching the requested schema."""


PAGE_CLASSIFICATION_SCHEMA = {
    "name": "page_classification",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "pages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "page_number": {"type": "integer"},
                        "question_ids": {"type": "array", "items": {"type": "string"}},
                        "confident": {"type": "boolean"},
                    },
                    "required": ["page_number", "question_ids", "confident"],
                },
            }
        },
        "required": ["pages"],
    },
}


def build_classification_text(question_ids):
    joined = ", ".join(question_ids)
    return f"Question IDs in this exam: {joined}\n\nLabel each attached page image with the question IDs it answers."


def classify_pages(provider, question_ids, image_data_urls):
    user_text = build_classification_text(question_ids)
    content = provider.complete_json(
        CLASSIFIER_PROMPT, user_text, PAGE_CLASSIFICATION_SCHEMA, image_data_urls
    )
    return parse_page_mapping(content, question_ids, len(image_data_urls))


def parse_page_mapping(content, question_ids, page_count):
    data = json.loads(content)
    mapping = {question_id: [] for question_id in question_ids}
    for page in data.get("pages", []):
        if not page.get("confident"):
            continue
        index = page.get("page_number", 0) - 1
        if index < 0 or index >= page_count:
            continue
        for raw_id in page.get("question_ids", []):
            question_id = normalise_question_id(raw_id)
            if question_id in mapping:
                mapping[question_id].append(index)
    return {question_id: sorted(set(indices)) for question_id, indices in mapping.items()}


class ScriptPages:
    def __init__(self, provider, question_ids):
        self.provider = provider
        self.question_ids = question_ids
        self._cache = {}

    def pages_for(self, pdf_path, question_id):
        pages, mapping = self._resolve(pdf_path)
        indices = mapping.get(question_id)
        if not indices:
            return pages
        return [pages[index] for index in indices]

    def _resolve(self, pdf_path):
        if pdf_path not in self._cache:
            pages = render_pdf_pages_as_data_urls(pdf_path)
            mapping = classify_pages(self.provider, self.question_ids, pages) if self.question_ids else {}
            self._cache[pdf_path] = (pages, mapping)
        return self._cache[pdf_path]
