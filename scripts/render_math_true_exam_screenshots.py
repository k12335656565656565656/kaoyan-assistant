"""Render bookmarked answer-book pages into resumable Mimo input images.

The answer books contain both question and answer pages. The year bookmarks are
used instead of hard-coded page numbers so the three exam versions can differ.
"""

import argparse
from pathlib import Path

import fitz


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PDF_NAMES = {
    "math1": "数学一真题【答案册】-带书签（1987年-2026年）.pdf",
    "math2": "数学二真题【答案册】-带书签（1987年-2026年）.pdf",
    "math3": "数学三真题【答案册】-带书签（1987年-2026年）.pdf",
}


def year_pages(document, start_year: int, end_year: int):
    bookmarks = {
        int(title.strip()): page - 1
        for level, title, page in document.get_toc()
        if level == 1 and title.strip().isdigit()
    }
    available = sorted(year for year in bookmarks if start_year <= year <= end_year)
    if len(available) != end_year - start_year + 1:
        missing = [year for year in range(start_year, end_year + 1) if year not in bookmarks]
        raise ValueError(f"missing year bookmarks: {missing}")
    for index, year in enumerate(available):
        first_page = bookmarks[year]
        next_page = bookmarks[available[index + 1]] if index + 1 < len(available) else len(document)
        yield year, range(first_page, next_page)


def render_exam(pdf_path: Path, output_root: Path, exam_type: str, start_year: int, end_year: int, dpi: int):
    document = fitz.open(pdf_path)
    rendered = 0
    for year, pages in year_pages(document, start_year, end_year):
        output_dir = output_root / str(year) / "screenshots" / exam_type
        output_dir.mkdir(parents=True, exist_ok=True)
        for page_index in pages:
            output_path = output_dir / f"pdf_page_{page_index + 1:04d}.png"
            if output_path.exists():
                continue
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
            pixmap.save(str(output_path))
            rendered += 1
    document.close()
    return rendered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exam-type", choices=tuple(PDF_NAMES), required=True)
    parser.add_argument("--start-year", type=int, default=2016)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--dpi", type=int, default=144)
    parser.add_argument("--pdf-root", type=Path, default=PROJECT_ROOT / "data" / "math_true_exam" / "raws")
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "data" / "math_true_exam" / "processed")
    args = parser.parse_args()
    pdf_path = args.pdf_root / PDF_NAMES[args.exam_type]
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")
    rendered = render_exam(pdf_path, args.output_root, args.exam_type, args.start_year, args.end_year, args.dpi)
    print(f"rendered={rendered} exam_type={args.exam_type} years={args.start_year}-{args.end_year}")


if __name__ == "__main__":
    main()
