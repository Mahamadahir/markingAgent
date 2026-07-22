import json
import unittest

from marking_agent.page_mapping import ScriptPages, parse_page_mapping


class ParsePageMappingTests(unittest.TestCase):
    def test_maps_confident_pages_to_questions(self):
        content = json.dumps(
            {
                "pages": [
                    {"page_number": 1, "question_ids": ["Q1"], "confident": True},
                    {"page_number": 2, "question_ids": ["Q1", "Q2"], "confident": True},
                    {"page_number": 3, "question_ids": ["Q2"], "confident": True},
                ]
            }
        )

        mapping = parse_page_mapping(content, ["Q1", "Q2"], page_count=3)

        self.assertEqual(mapping, {"Q1": [0, 1], "Q2": [1, 2]})

    def test_ignores_unconfident_and_out_of_range_pages(self):
        content = json.dumps(
            {
                "pages": [
                    {"page_number": 1, "question_ids": ["Q1"], "confident": False},
                    {"page_number": 9, "question_ids": ["Q1"], "confident": True},
                ]
            }
        )

        mapping = parse_page_mapping(content, ["Q1"], page_count=3)

        self.assertEqual(mapping, {"Q1": []})

    def test_normalises_returned_question_ids(self):
        content = json.dumps({"pages": [{"page_number": 1, "question_ids": ["question 1"], "confident": True}]})

        mapping = parse_page_mapping(content, ["Q1"], page_count=1)

        self.assertEqual(mapping, {"Q1": [0]})


class FakeProvider:
    def __init__(self, mapping_json):
        self.mapping_json = mapping_json
        self.calls = 0

    def complete_json(self, system_prompt, user_text, schema, image_data_urls=None):
        self.calls += 1
        return self.mapping_json


class ScriptPagesTests(unittest.TestCase):
    def test_returns_only_mapped_pages_for_a_question(self):
        resolver = ScriptPages(FakeProvider("{}"), ["Q1", "Q2"])

        # Prime the cache by hand to avoid real PDF rendering.
        resolver._cache["a.pdf"] = (["p0", "p1", "p2"], {"Q1": [1], "Q2": []})

        self.assertEqual(resolver.pages_for("a.pdf", "Q1"), ["p1"])

    def test_falls_back_to_whole_script_when_no_pages_mapped(self):
        provider = FakeProvider("{}")
        resolver = ScriptPages(provider, ["Q1", "Q2"])
        pages = ["p0", "p1"]
        resolver._cache["a.pdf"] = (pages, {"Q1": [], "Q2": [1]})

        self.assertEqual(resolver.pages_for("a.pdf", "Q1"), ["p0", "p1"])


if __name__ == "__main__":
    unittest.main()
