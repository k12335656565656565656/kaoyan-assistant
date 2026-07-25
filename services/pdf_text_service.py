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
    "研池大叔",
    "弘毅考研",
    "创梦资料",
    "后续更新关注公众号",
    "永久联系微信",
)


def extract_pdf_text(file_path, max_chars=None, progress_callback=None):
    """Extract text and page-level diagnostics from a PDF using PyMuPDF."""
    import fitz

    doc = fitz.open(str(Path(file_path)))
    page_texts = []
    page_diagnostics = []
    try:
        total_pages = len(doc)
        for page_index, page in enumerate(doc, start=1):
            if progress_callback:
                progress_callback(page_index - 1, total_pages, f"正在检查第 {page_index}/{total_pages} 页 PDF 结构")
            raw_text = (page.get_text() or "").strip()
            if raw_text:
                page_texts.append(f"=== 第{page_index}页 ===\n{raw_text}")
            else:
                page_texts.append("")
            page_diagnostics.append(_analyze_page(page_index, page, raw_text))
        if progress_callback:
            progress_callback(total_pages, total_pages, "PDF 结构检查完成")
    finally:
        doc.close()

    combined_text = "\n\n".join(text for text in page_texts if text.strip())
    empty_page_count = sum(1 for text in page_texts if not text.strip())
    pdf_diagnostics = analyze_pdf_page_diagnostics(page_diagnostics, total_page_count=len(page_texts))
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


def inspect_pdf_for_ocr(file_path, sample_pages=12, progress_callback=None):
    """Quickly sample a PDF to decide whether full text extraction should be skipped."""
    import fitz

    doc = fitz.open(str(Path(file_path)))
    page_count = len(doc)
    page_indices = _select_sample_page_indices(page_count, sample_pages)
    page_diagnostics = []
    page_texts = []
    try:
        for sample_index, page_index in enumerate(page_indices, start=1):
            if progress_callback:
                progress_callback(
                    sample_index - 1,
                    len(page_indices),
                    f"正在抽样检查第 {page_index + 1}/{page_count} 页 PDF 结构",
                )
            page = doc[page_index]
            raw_text = (page.get_text() or "").strip()
            if raw_text:
                page_texts.append(f"=== 第{page_index + 1}页 ===\n{raw_text}")
            else:
                page_texts.append("")
            page_diagnostics.append(_analyze_page(page_index + 1, page, raw_text))
        if progress_callback:
            progress_callback(len(page_indices), len(page_indices), "PDF 抽样检查完成")
    finally:
        doc.close()

    return {
        "text": "\n\n".join(text for text in page_texts if text.strip()),
        "page_count": page_count,
        "diagnostic_page_count": len(page_diagnostics),
        "sampled_pages": [index + 1 for index in page_indices],
        "empty_page_count": sum(1 for text in page_texts if not text.strip()),
        "page_diagnostics": page_diagnostics,
        "pdf_diagnostics": analyze_pdf_page_diagnostics(
            page_diagnostics,
            total_page_count=page_count,
        ),
    }


def analyze_pdf_page_diagnostics(page_diagnostics: list[dict], total_page_count=None) -> dict:
    diagnostic_page_count = len(page_diagnostics)
    page_count = total_page_count or diagnostic_page_count
    if not diagnostic_page_count:
        return {
            "page_count": page_count,
            "diagnostic_page_count": 0,
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

    ratio_base = max(diagnostic_page_count, 1)
    image_dominant_ratio = image_dominant_pages / ratio_base
    low_text_ratio = low_text_pages / ratio_base
    watermark_like_ratio = watermark_like_pages / ratio_base
    repeated_text_ratio = repeated_text_pages / ratio_base

    reasons = []
    if image_dominant_ratio >= 0.5:
        reasons.append(f"抽样 {image_dominant_pages}/{diagnostic_page_count} 页由整页图片主导")
    if repeated_text_ratio >= 0.5:
        reasons.append(f"抽样 {repeated_text_pages}/{diagnostic_page_count} 页存在重复文字层")
    if watermark_like_ratio >= 0.5:
        reasons.append(f"抽样 {watermark_like_pages}/{diagnostic_page_count} 页文字层高度像水印/推广信息")
    if low_text_ratio >= 0.75:
        reasons.append(f"抽样 {low_text_pages}/{diagnostic_page_count} 页可提取文字过少")

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
        "diagnostic_page_count": diagnostic_page_count,
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


def _select_sample_page_indices(page_count, sample_pages):
    if page_count <= 0:
        return []
    sample_count = min(max(int(sample_pages or 1), 1), page_count)
    if sample_count == page_count:
        return list(range(page_count))
    if sample_count == 1:
        return [0]

    indexes = {
        round(position * (page_count - 1) / (sample_count - 1))
        for position in range(sample_count)
    }
    return sorted(indexes)


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
