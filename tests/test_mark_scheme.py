import unittest

from marking_agent.mark_scheme import extract_mark_scheme_snippet, list_question_ids


class MarkSchemeTests(unittest.TestCase):
    def test_extracts_matching_question_section(self):
        mark_scheme = "# Q1\nOne\n\n# Q2\nTwo\n\n# Q3\nThree"

        snippet = extract_mark_scheme_snippet(mark_scheme, "Q2")

        self.assertEqual(snippet, "# Q2\nTwo")

    def test_accepts_question_word_heading(self):
        mark_scheme = "Question 1\nOne\n\nQuestion 2\nTwo"

        snippet = extract_mark_scheme_snippet(mark_scheme, "Q1")

        self.assertEqual(snippet, "Question 1\nOne")

    def test_falls_back_to_full_mark_scheme_when_no_heading_matches(self):
        mark_scheme = "General marking notes"

        snippet = extract_mark_scheme_snippet(mark_scheme, "Q9")

        self.assertEqual(snippet, mark_scheme)

    def test_lists_question_ids_in_order_without_duplicates(self):
        mark_scheme = "# Q1\nOne\n\n# Q2\nTwo\n\n# Q1\nMore of one"

        self.assertEqual(list_question_ids(mark_scheme), ["Q1", "Q2"])

    def test_lists_no_questions_when_no_headings(self):
        self.assertEqual(list_question_ids("General marking notes"), [])


if __name__ == "__main__":
    unittest.main()
