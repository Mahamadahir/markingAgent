def extract_pdf_text(path):
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError(
            "PDF extraction requires pypdf. Run: pip install -r requirements.txt"
        ) from error

    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    reader = PdfReader(str(path))
    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": page_number, "text": text.strip()})

    return pages


def write_extracted_text(pages, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []

    for page in pages:
        lines.append(f"--- Page {page['page']} ---")
        lines.append(page["text"])
        lines.append("")

    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
