import tempfile
import unittest
from pathlib import Path
from unittest import mock

from marking_agent import app_service
from marking_agent.app_service import AppService, normalise_action
from marking_agent.pdf_submissions import FULL_SCRIPT_QUESTION_ID
from marking_agent.state import APPROVED, OVERRIDDEN, save_provisional_evaluation
from tests.helpers import FakeProvider, full_script_evaluation, write_submissions


class NormaliseActionTests(unittest.TestCase):
    def test_maps_verb_forms_to_status_constants(self):
        self.assertEqual(normalise_action("approve"), APPROVED)
        self.assertEqual(normalise_action(" override "), OVERRIDDEN)

    def test_accepts_status_constants_directly(self):
        self.assertEqual(normalise_action(APPROVED), APPROVED)
        self.assertEqual(normalise_action(OVERRIDDEN), OVERRIDDEN)

    def test_rejects_unknown_action(self):
        with self.assertRaises(ValueError):
            normalise_action("reject")


class AppServiceTests(unittest.TestCase):
    def build_service(self, directory):
        service = AppService(
            db_path=directory / "state.sqlite3",
            output_path=directory / "grades.csv",
            exam_name="Paper 1",
        )
        self.addCleanup(service.close)
        return service

    def test_creates_and_lists_default_exam(self):
        with tempfile.TemporaryDirectory() as raw:
            service = self.build_service(Path(raw))

            self.assertTrue(any(exam["exam_id"] == service.exam_id for exam in service.exams()))

    def test_provider_for_remembers_choice_on_the_exam(self):
        from marking_agent.config import provider_settings

        with tempfile.TemporaryDirectory() as raw:
            service = self.build_service(Path(raw))

            service.provider_for(provider_settings("claude-opus-4-8", provider="anthropic"))

            self.assertEqual(service.stored_provider(), {"provider": "anthropic", "model": "claude-opus-4-8"})

    def test_stored_provider_is_none_before_any_grading(self):
        with tempfile.TemporaryDirectory() as raw:
            service = self.build_service(Path(raw))

            self.assertIsNone(service.stored_provider())

    def test_set_exam_switches_active_exam(self):
        with tempfile.TemporaryDirectory() as raw:
            service = self.build_service(Path(raw))

            chemistry_id = service.set_exam(exam_id="chemistry", exam_name="Chemistry")

            self.assertEqual(service.exam_id, chemistry_id)
            self.assertEqual(chemistry_id, "chemistry")

    def test_load_exam_items_reports_pending_status(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            write_submissions(directory)
            service = self.build_service(directory)

            items = service.load_exam_items(directory)

            self.assertEqual([item["student_id"] for item in items], ["STUDENT_001", "STUDENT_002"])
            self.assertEqual({item["status"] for item in items}, {"PENDING"})

    def test_grade_item_saves_provisional_evaluation(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            write_submissions(directory)
            mark_scheme_path = directory / "scheme.txt"
            mark_scheme_path.write_text("Full script guidance", encoding="utf-8")
            service = self.build_service(directory)
            item = service.load_exam_items(directory)[0]

            settings = object()
            with mock.patch.object(app_service, "build_provider", return_value=FakeProvider(full_script_evaluation("STUDENT_001"))):
                with mock.patch("marking_agent.page_mapping.render_pdf_pages_as_data_urls", return_value=["page"]):
                    with mock.patch.object(app_service, "grade_pdf_images", return_value=full_script_evaluation("STUDENT_001")) as graded:
                        evaluation = service.grade_item(settings, mark_scheme_path, item)

            self.assertEqual(evaluation["student_id"], "STUDENT_001")
            graded.assert_called_once()
            self.assertEqual(service.get_saved_evaluation("STUDENT_001", FULL_SCRIPT_QUESTION_ID)["proposed_marks_awarded"], 2)

    def test_grade_item_resumes_saved_evaluation_without_regrading(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            write_submissions(directory)
            mark_scheme_path = directory / "scheme.txt"
            mark_scheme_path.write_text("guidance", encoding="utf-8")
            service = self.build_service(directory)
            item = service.load_exam_items(directory)[0]
            save_provisional_evaluation(service.connection, service.exam_id, "STUDENT_001", FULL_SCRIPT_QUESTION_ID, full_script_evaluation("STUDENT_001", marks=1))

            with mock.patch.object(app_service, "grade_pdf_images") as graded:
                evaluation = service.grade_item(object(), mark_scheme_path, item)

            graded.assert_not_called()
            self.assertEqual(evaluation["proposed_marks_awarded"], 1)

    def test_save_decision_validates_and_exports_csv(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            service = self.build_service(directory)
            evaluation = full_script_evaluation("STUDENT_001")

            normalised = service.save_decision("STUDENT_001", FULL_SCRIPT_QUESTION_ID, evaluation, APPROVED, "2", "Approved AI assessment.")

            self.assertEqual(normalised, "2")
            self.assertTrue((directory / "grades.csv").exists())
            self.assertEqual(len(service.records(final_only=True)), 1)

    def test_save_decision_rejects_out_of_range_score(self):
        with tempfile.TemporaryDirectory() as raw:
            service = self.build_service(Path(raw))
            evaluation = full_script_evaluation("STUDENT_001")

            with self.assertRaises(ValueError):
                service.save_decision("STUDENT_001", FULL_SCRIPT_QUESTION_ID, evaluation, APPROVED, "9", "note")


if __name__ == "__main__":
    unittest.main()
