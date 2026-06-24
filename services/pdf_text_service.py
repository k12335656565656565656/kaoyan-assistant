from __future__ import annotations

from collections import Counter
from pathlib import Path
import re


_WATERMARK_HINTS = (
    "cskaoyan",
    "github.com",
    "微信公众号",
    "计算机与软件考研",
    "免费分享",
    "复试资料",
    "考研资讯",
)


def extract_pdf_text(file_path, max_chars=None):
    """Extract text and page-level diagnostics from a PDF using PyMuPDF."""
    import fitz

    doc = fitz.open(str(Path(file_path)))
    page_texts = []
    page_diagnostics = []
    try:
        for page_index, page in enumerate(doc, start=1):
            raw_text = (page.get_text() or "").strip()
            if raw_text:
                page_texts.append(f"=== 第{page_index}页 ===\n{raw_text}")
            else:
                page_texts.append("")
            page_diagnostics.append(_analyze_page(page_index, page, raw_text))
    finally:
        doc.close()

    combined_text = "\n\n".join(text for text in page_texts if text.strip())
    empty_page_count = sum(1 for text in page_texts if not text.strip())
    pdf_diagnostics = analyze_pdf_page_diagnostics(page_diagnostics)
    if max_chars is not None:
        combined_text = combined_text[:max_chars]

    return {
        "text": combined_text,
        "page_count": len(page_texts),
        "page_texts": page_texts,
        "empty_page_count": empty_page_count,
        "page_diagnostics": page_diagnostics,
        "pdf_diagnostics": pdf_diagnostics,
    }


def analyze_pdf_page_diagnostics(page_diagnostics: list[dict]) -> dict:
    page_count = len(page_diagnostics)
    if not page_count:
        return {
            "page_count": 0,
            "image_dominant_pages": 0,
            "image_dominant_ratio": 0.0,
            "low_text_pages": 0,
            "low_text_ratio": 0.0,
            "watermark_like_pages": 0,
            "watermark_like_ratio": 0.0,
            "repeated_text_pages": 0,
            "repeated_text_ratio": 0.0,
            "max_repeated_text_group": 0,
            "needs_ocr": False,
            "reasons": [],
        }

    repeated_counter = Counter(
        item["normalized_text"]
        for item in page_diagnostics
        if item.get("normalized_text")
    )
    max_repeated_text_group = repeated_counter.most_common(1)[0][1] if repeated_counter else 0
    repeated_text_pages = sum(
        1
        for item in page_diagnostics
        if item.get("normalized_text") and repeated_counter[item["normalized_text"]] > 1
    )
    image_dominant_pages = sum(1 for item in page_diagnostics if item.get("is_image_dominant"))
    low_text_pages = sum(1 for item in page_diagnostics if item.get("text_chars", 0) < 180)
    watermark_like_pages = sum(1 for item in page_diagnostics if item.get("has_watermark_hint"))

    image_dominant_ratio = image_dominant_pages / page_count
    low_text_ratio = low_text_pages / page_count
    watermark_like_ratio = watermark_like_pages / page_count
    repeated_text_ratio = repeated_text_pages / page_count

    reasons = []
    if image_dominant_ratio >= 0.5:
        reasons.append(f"{image_dominant_pages}/{page_count} 页由整页图片主导")
    if repeated_text_ratio >= 0.5:
        reasons.append(f"{repeated_text_pages}/{page_count} 页存在重复文字层")
    if watermark_like_ratio >= 0.5:
        reasons.append(f"{watermark_like_pages}/{page_count} 页文字层高度像水印/推广信息")
    if low_text_ratio >= 0.75:
        reasons.append(f"{low_text_pages}/{page_count} 页可提取文字过少")

    needs_ocr = bool(
        (
            image_dominant_ratio >= 0.5
            and repeated_text_ratio >= 0.5
            and watermark_like_ratio >= 0.5
        )
        or (
            image_dominant_ratio >= 0.75
            and low_text_ratio >= 0.75
        )
    )

    return {
        "page_count": page_count,
        "image_dominant_pages": image_dominant_pages,
        "image_dominant_ratio": round(image_dominant_ratio, 4),
        "low_text_pages": low_text_pages,
        "low_text_ratio": round(low_text_ratio, 4),
        "watermark_like_pages": watermark_like_pages,
        "watermark_like_ratio": round(watermark_like_ratio, 4),
        "repeated_text_pages": repeated_text_pages,
        "repeated_text_ratio": round(repeated_text_ratio, 4),
        "max_repeated_text_group": max_repeated_text_group,
        "needs_ocr": needs_ocr,
        "reasons": reasons,
    }


def _analyze_page(page_index, page, raw_text: str) -> dict:
    page_area = max(float(page.rect.width * page.rect.height), 1.0)
    text_chars = len((raw_text or "").strip())
    normalized_text = _normalize_page_text(raw_text)
    watermarks = [hint for hint in _WATERMARK_HINTS if hint.lower() in normalized_text.lower()]

    image_blocks = []
    page_dict = page.get_text("dict")
    for block in page_dict.get("blocks", []):
        if block.get("type") != 1:
            continue
        bbox = block.get("bbox") or (0, 0, 0, 0)
        width = max(float(bbox[2] - bbox[0]), 0.0)
        height = max(float(bbox[3] - bbox[1]), 0.0)
        image_blocks.append((width * height) / page_area)

    largest_image_ratio = max(image_blocks) if image_blocks else 0.0
    image_area_ratio = sum(image_blocks)
    return {
        "page_index": page_index,
        "text_chars": text_chars,
        "normalized_text": normalized_text,
        "image_count": len(image_blocks),
        "largest_image_ratio": round(largest_image_ratio, 4),
        "image_area_ratio": round(image_area_ratio, 4),
        "is_image_dominant": largest_image_ratio >= 0.7 or image_area_ratio >= 0.85,
        "has_watermark_hint": bool(watermarks),
        "watermark_hints": watermarks,
    }


def _normalize_page_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    compact = compact.replace("\x00", "")
    return compact[:800]
