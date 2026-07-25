"""Audit local 408/313 PDFs before promoting content into the archetype library."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys


NOISE_MARKERS = (
    "公众号",
    "微信",
    "扫码",
    "二维码",
    "免费分享",
    "领取资料",
    "github.com",
    "cskaoyan",
    "研池大叔",
    "弘毅考研",
    "创梦资料",
)


def audit_pdf(path: Path, sample_pages: int = 12) -> dict:
    page_count, page_texts = extract_sample_text(path, sample_pages)
    normalized_pages = [_compact(text) for text in page_texts]
    nonempty = [text for text in normalized_pages if text]
    text_chars = sum(len(text) for text in nonempty)
    cjk_chars = sum(len(re.findall(r"[\u4e00-\u9fff]", text)) for text in nonempty)
    usable_chars = sum(
        len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))
        for text in nonempty
    )
    usable_ratio = usable_chars / max(text_chars, 1)
    noise_pages = sum(
        1
        for text in normalized_pages
        if any(marker.lower() in text.lower() for marker in NOISE_MARKERS)
    )
    repeated_pages = sum(
        count
        for text, count in Counter(nonempty).items()
        if text and count > 1
    )
    sampled = len(page_texts)
    avg_chars = text_chars / max(sampled, 1)

    if avg_chars < 80 or not nonempty:
        extraction_status = "ocr_required"
    elif usable_ratio < 0.55:
        extraction_status = "text_layer_corrupt"
    elif noise_pages >= max(2, sampled // 2) and avg_chars < 220:
        extraction_status = "watermark_dominant"
    elif noise_pages:
        extraction_status = "text_usable_after_noise_cleaning"
    else:
        extraction_status = "text_usable"

    return {
        # Reports may be committed or shared. Never persist the caller's
        # workstation path when the filename is sufficient for source review.
        "file": path.name,
        "sha256": _sha256(path),
        "page_count": page_count,
        "sampled_pages": sampled,
        "sample_text_chars": text_chars,
        "sample_cjk_chars": cjk_chars,
        "usable_char_ratio": round(usable_ratio, 4),
        "noise_pages": noise_pages,
        "repeated_text_pages": repeated_pages,
        "extraction_status": extraction_status,
        "promotion_rule": _promotion_rule(extraction_status),
    }


def extract_sample_text(path: Path, sample_pages: int) -> tuple[int, list[str]]:
    try:
        import fitz
    except ImportError:
        fitz = None
    if fitz is not None:
        doc = fitz.open(str(path))
        try:
            indexes = select_page_indexes(len(doc), sample_pages)
            return len(doc), [(doc[index].get_text("text") or "") for index in indexes]
        finally:
            doc.close()

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("需要安装 PyMuPDF 或 pypdf 才能审计PDF。") from exc
    reader = PdfReader(str(path))
    indexes = select_page_indexes(len(reader.pages), sample_pages)
    texts = []
    for index in indexes:
        page = reader.pages[index]
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except TypeError:
            text = page.extract_text() or ""
        texts.append(text)
    return len(reader.pages), texts


def select_page_indexes(page_count: int, sample_pages: int) -> list[int]:
    if page_count <= 0:
        return []
    count = min(max(int(sample_pages or 1), 1), page_count)
    if count == page_count:
        return list(range(page_count))
    if count == 1:
        return [0]
    return sorted(
        {
            round(position * (page_count - 1) / (count - 1))
            for position in range(count)
        }
    )


def _promotion_rule(status: str) -> str:
    rules = {
        "text_usable": "可进入题号切分；仍需人工抽查题干与页码。",
        "text_usable_after_noise_cleaning": "先清除广告/水印并核对题号连续性，再进入候选库。",
        "watermark_dominant": "原生文字层不得入库；渲染页面后OCR，并以跨页位置和广告词去噪。",
        "text_layer_corrupt": "原生文字层不得入库；改用页面渲染/OCR并做结构校验。",
        "ocr_required": "逐页渲染/OCR；必须恢复题号、选项和小问结构后才能入库。",
    }
    return rules[status]


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").replace("\x00", ""))[:12000]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--sample-pages", type=int, default=12)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = sorted(
        {
            path.resolve()
            for root in args.roots
            for path in (root.rglob("*.pdf") if root.is_dir() else [root])
            if path.suffix.lower() == ".pdf"
        }
    )
    report = {
        "schema_version": 1,
        "files": [audit_pdf(path, args.sample_pages) for path in paths],
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
