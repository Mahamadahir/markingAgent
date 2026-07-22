OCR_NEVER = "never"
OCR_AUTO = "auto"
OCR_ALWAYS = "always"
OCR_MODES = [OCR_NEVER, OCR_AUTO, OCR_ALWAYS]

MIN_EMBEDDED_TEXT_CHARS = 10
OCR_DPI = 300


def extract_pdf_text(path, ocr_mode=OCR_NEVER):
    if ocr_mode not in OCR_MODES:
        raise ValueError(f"Unknown OCR mode: {ocr_mode}")
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    if ocr_mode == OCR_ALWAYS:
        ocr_texts = ocr_page_texts(path)
        return [{"page": index + 1, "text": ocr_texts[index]} for index in sorted(ocr_texts)]

    pages = embedded_text_pages(path)
    if ocr_mode == OCR_AUTO:
        missing = [index for index, page in enumerate(pages) if len(page["text"]) < MIN_EMBEDDED_TEXT_CHARS]
        if missing:
            ocr_texts = ocr_page_texts(path, missing)
            for index in missing:
                pages[index]["text"] = ocr_texts[index]
    return pages


def embedded_text_pages(path):
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError(
            "PDF extraction requires pypdf. Run: pip install -r requirements.txt"
        ) from error

    reader = PdfReader(str(path))
    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": page_number, "text": text.strip()})
    return pages


def ocr_page_texts(path, page_indices=None):
    fitz = import_pymupdf()
    pytesseract = import_pytesseract()
    from io import BytesIO

    from PIL import Image

    texts = {}
    with fitz.open(path) as document:
        indices = range(document.page_count) if page_indices is None else page_indices
        for index in indices:
            page = document.load_page(index)
            pixmap = page.get_pixmap(dpi=OCR_DPI, alpha=False)
            image = Image.open(BytesIO(pixmap.tobytes("png")))
            texts[index] = pytesseract.image_to_string(image).strip()
    return texts


def import_pymupdf():
    try:
        import fitz
    except ImportError as error:
        raise RuntimeError(
            "OCR requires PyMuPDF. Run: pip install -r requirements.txt"
        ) from error
    return fitz


def import_pytesseract():
    try:
        import pytesseract
    except ImportError as error:
        raise RuntimeError(
            "OCR requires pytesseract and the Tesseract binary. "
            "Run: pip install -r requirements.txt and install tesseract-ocr."
        ) from error
    return pytesseract


def write_extracted_text(pages, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []

    for page in pages:
        lines.append(f"--- Page {page['page']} ---")
        lines.append(page["text"])
        lines.append("")

    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
