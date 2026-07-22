import tempfile
import unittest
from pathlib import Path
from unittest import mock

from marking_agent import pdf_extract
from marking_agent.pdf_extract import extract_pdf_text


class ExtractPdfTextTests(unittest.TestCase):
    def _pdf(self, directory):
        path = Path(directory) / "scheme.pdf"
        path.write_bytes(b"%PDF-1.4")
        return path

    def test_rejects_unknown_ocr_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                extract_pdf_text(self._pdf(directory), ocr_mode="magic")

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            extract_pdf_text(Path("/no/such/file.pdf"))

    def test_never_returns_embedded_text_without_ocr(self):
        with tempfile.TemporaryDirectory() as directory:
            pages = [{"page": 1, "text": "Q1 marks"}]
            with mock.patch.object(pdf_extract, "embedded_text_pages", return_value=pages):
                with mock.patch.object(pdf_extract, "ocr_page_texts") as ocr:
                    result = extract_pdf_text(self._pdf(directory), ocr_mode="never")

            ocr.assert_not_called()
            self.assertEqual(result, pages)

    def test_auto_ocrs_only_pages_without_text(self):
        with tempfile.TemporaryDirectory() as directory:
            pages = [{"page": 1, "text": "Q1 full marks scheme"}, {"page": 2, "text": ""}]
            with mock.patch.object(pdf_extract, "embedded_text_pages", return_value=pages):
                with mock.patch.object(pdf_extract, "ocr_page_texts", return_value={1: "recovered"}) as ocr:
                    result = extract_pdf_text(self._pdf(directory), ocr_mode="auto")

            ocr.assert_called_once_with(mock.ANY, [1])
            self.assertEqual(result[1]["text"], "recovered")

    def test_always_ocrs_every_page_and_ignores_embedded(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(pdf_extract, "embedded_text_pages") as embedded:
                with mock.patch.object(pdf_extract, "ocr_page_texts", return_value={0: "a", 1: "b"}):
                    result = extract_pdf_text(self._pdf(directory), ocr_mode="always")

            embedded.assert_not_called()
            self.assertEqual(result, [{"page": 1, "text": "a"}, {"page": 2, "text": "b"}])


if __name__ == "__main__":
    unittest.main()
