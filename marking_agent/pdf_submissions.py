import base64
from pathlib import Path


FULL_SCRIPT_QUESTION_ID = "FULL_SCRIPT"
DEFAULT_RENDER_DPI = 180
DEFAULT_MAX_PAGES = 12


def load_pdf_submissions(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Student submissions path not found: {path}")

    pdf_paths = collect_pdf_paths(path)
    if not pdf_paths:
        raise ValueError(f"No PDF submissions found in: {path}")

    return [submission_from_pdf(pdf_path) for pdf_path in pdf_paths]


def collect_pdf_paths(path):
    if path.is_file():
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"Student submission must be a PDF: {path}")
        return [path]

    if path.is_dir():
        return sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() == ".pdf")

    raise ValueError(f"Student submissions path is not a file or directory: {path}")


def submission_from_pdf(pdf_path):
    return {
        "student_id": pdf_path.stem,
        "question_id": FULL_SCRIPT_QUESTION_ID,
        "pdf_path": str(pdf_path),
    }


def render_pdf_pages_as_data_urls(pdf_path, dpi=DEFAULT_RENDER_DPI, max_pages=DEFAULT_MAX_PAGES):
    try:
        import fitz
    except ImportError as error:
        raise RuntimeError(
            "Handwritten PDF grading requires PyMuPDF. Run: pip install -r requirements.txt"
        ) from error

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"Student response PDF not found: {path}")

    data_urls = []
    with fitz.open(path) as document:
        if document.page_count == 0:
            raise ValueError(f"Student response PDF has no pages: {path}")

        for page_index in range(min(document.page_count, max_pages)):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            data_urls.append(image_data_url(pixmap.tobytes("png"), "image/png"))

    return data_urls


def image_data_url(image_bytes, mime_type):
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
