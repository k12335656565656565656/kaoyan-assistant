from pathlib import Path


def extract_pdf_text(file_path, max_chars=8000):
    """Extract text and per-page stats from a PDF using PyMuPDF."""
    import fitz

    doc = fitz.open(str(Path(file_path)))
    page_texts = []
    try:
        for page in doc:
            page_texts.append(page.get_text() or "")
    finally:
        doc.close()

    combined_text = "".join(page_texts)
    empty_page_count = sum(1 for text in page_texts if not text.strip())
    return {
        "text": combined_text[:max_chars],
        "page_count": len(page_texts),
        "page_texts": page_texts,
        "empty_page_count": empty_page_count,
    }
