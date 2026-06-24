"""Adaptive OCR helpers with a fast primary engine and quality-based fallback."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from services.paddle_ocr_service import extract_text_from_image_bytes


@dataclass
class OCRTextResult:
    text: str
    engine: str
    average_confidence: float
    quality_score: float
    enhanced: bool = False


@lru_cache(maxsize=1)
def _get_rapid_ocr():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        return None
    return RapidOCR()


def is_rapid_ocr_available() -> bool:
    return _get_rapid_ocr() is not None


def extract_text_adaptively(
    image_bytes: bytes,
    *,
    lang: str = "ch",
    allow_paddle_fallback: bool = True,
) -> OCRTextResult:
    """Run fast OCR first, then retry only when quality signals are weak."""
    rapid_result = _run_rapid_ocr(image_bytes)
    best_result = rapid_result

    if rapid_result and not _is_result_acceptable(rapid_result):
        enhanced_bytes = _enhance_document_image(image_bytes)
        if enhanced_bytes:
            enhanced_result = _run_rapid_ocr(enhanced_bytes, enhanced=True)
            best_result = _choose_better_result(best_result, enhanced_result)

    if best_result and _is_result_acceptable(best_result):
        return best_result

    if allow_paddle_fallback:
        paddle_text = extract_text_from_image_bytes(image_bytes, lang=lang)
        paddle_result = _build_result(paddle_text, "PaddleOCR", 0.72)
        best_result = _choose_better_result(best_result, paddle_result)

    return best_result or OCRTextResult(
        text="",
        engine="unavailable",
        average_confidence=0.0,
        quality_score=0.0,
    )


def extract_pdf_text_adaptively(
    file_path,
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    max_pages: int = 20,
    max_chars: int | None = None,
) -> tuple[str, dict]:
    """OCR image-dominant PDF pages and preserve page anchors."""
    import fitz

    doc = fitz.open(str(file_path))
    page_texts = []
    raw_page_lines = []
    engines = []
    quality_scores = []
    enhanced_pages = 0
    total_pages = min(len(doc), max_pages)

    try:
        for page_num in range(total_pages):
            if progress_callback:
                progress_callback(page_num, total_pages, f"正在识别第 {page_num + 1}/{total_pages} 页")

            page = doc[page_num]
            page_image_bytes = _extract_dominant_page_image_bytes(doc, page)
            if not page_image_bytes:
                pix = page.get_pixmap(dpi=130)
                page_image_bytes = pix.tobytes("png")

            result = extract_text_adaptively(page_image_bytes)
            if result.text:
                raw_page_lines.append([line.strip() for line in result.text.splitlines() if line.strip()])
            else:
                raw_page_lines.append([])
            engines.append(result.engine)
            quality_scores.append(result.quality_score)
            enhanced_pages += int(result.enhanced)
    finally:
        doc.close()

    cleaned_page_lines, repeated_lines_removed = _remove_repeated_page_lines(raw_page_lines)
    for page_num, lines in enumerate(cleaned_page_lines, start=1):
        if lines:
            page_texts.append(f"=== 第{page_num}页 ===\n" + "\n".join(lines))

    if progress_callback:
        progress_callback(total_pages, total_pages, "OCR 识别完成")

    report = {
        "pages_processed": total_pages,
        "engines": engines,
        "primary_engine": _most_common(engines),
        "average_quality": round(sum(quality_scores) / max(len(quality_scores), 1), 4),
        "enhanced_pages": enhanced_pages,
        "repeated_lines_removed": repeated_lines_removed,
    }
    combined_text = "\n\n".join(page_texts)
    if max_chars is not None:
        combined_text = combined_text[:max_chars]
    return combined_text, report


def _run_rapid_ocr(image_bytes: bytes, *, enhanced: bool = False) -> OCRTextResult | None:
    engine = _get_rapid_ocr()
    if engine is None or not image_bytes:
        return None

    try:
        output, _elapsed = engine(image_bytes)
    except Exception:
        return None

    entries = []
    for item in output or []:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        text = str(item[1]).strip()
        if not text:
            continue
        try:
            confidence = float(item[2])
        except (TypeError, ValueError):
            confidence = 0.0
        entries.append((item[0], text, confidence))

    entries = _sort_ocr_entries(entries)
    texts = [text for _box, text, _confidence in entries]
    confidences = [confidence for _box, _text, confidence in entries]

    average_confidence = sum(confidences) / max(len(confidences), 1)
    return _build_result(
        "\n".join(texts),
        "RapidOCR",
        average_confidence,
        enhanced=enhanced,
    )


def _build_result(
    text: str,
    engine: str,
    average_confidence: float,
    *,
    enhanced: bool = False,
) -> OCRTextResult:
    compact = re.sub(r"\s+", "", text or "")
    usable_chars = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", compact))
    usable_ratio = usable_chars / max(len(compact), 1)
    length_score = min(len(compact) / 500, 1.0)
    quality_score = (
        max(0.0, min(average_confidence, 1.0)) * 0.65
        + usable_ratio * 0.2
        + length_score * 0.15
    )
    return OCRTextResult(
        text=(text or "").strip(),
        engine=engine,
        average_confidence=round(average_confidence, 4),
        quality_score=round(quality_score, 4),
        enhanced=enhanced,
    )


def _is_result_acceptable(result: OCRTextResult) -> bool:
    compact_length = len(re.sub(r"\s+", "", result.text or ""))
    return compact_length >= 80 and result.quality_score >= 0.58


def _choose_better_result(
    current: OCRTextResult | None,
    candidate: OCRTextResult | None,
) -> OCRTextResult | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return candidate if candidate.quality_score > current.quality_score else current


def _enhance_document_image(image_bytes: bytes) -> bytes | None:
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps

        image = Image.open(io.BytesIO(image_bytes)).convert("L")
        image = ImageOps.autocontrast(image, cutoff=1)
        if image.width < 1600:
            scale = 1600 / max(image.width, 1)
            image = image.resize(
                (1600, max(int(image.height * scale), 1)),
                Image.Resampling.LANCZOS,
            )
        image = image.filter(ImageFilter.SHARPEN)
        image = ImageEnhance.Contrast(image).enhance(1.12).convert("RGB")
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()
    except Exception:
        return None


def _extract_dominant_page_image_bytes(doc, page):
    page_area = max(float(page.rect.width * page.rect.height), 1.0)
    for image_info in page.get_images(full=True):
        xref = image_info[0]
        for bbox_info in page.get_image_rects(xref, transform=False):
            image_area = max(float(bbox_info.width * bbox_info.height), 0.0)
            if image_area / page_area < 0.7:
                continue
            try:
                return doc.extract_image(xref).get("image")
            except Exception:
                return None
    return None


def _most_common(values: list[str]) -> str:
    if not values:
        return "unknown"
    return max(set(values), key=values.count)


def _sort_ocr_entries(entries):
    normalized = []
    for box, text, confidence in entries:
        try:
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            x_min = min(xs)
            y_min = min(ys)
            y_max = max(ys)
        except Exception:
            x_min = 0.0
            y_min = float(len(normalized) * 20)
            y_max = y_min + 10.0
        normalized.append(
            {
                "box": box,
                "text": text,
                "confidence": confidence,
                "x": x_min,
                "y": (y_min + y_max) / 2,
                "height": max(y_max - y_min, 1.0),
            }
        )

    normalized.sort(key=lambda item: (item["y"], item["x"]))
    rows = []
    for entry in normalized:
        if not rows:
            rows.append([entry])
            continue
        row = rows[-1]
        row_y = sum(item["y"] for item in row) / len(row)
        tolerance = max(8.0, sum(item["height"] for item in row) / len(row) * 0.55)
        if abs(entry["y"] - row_y) <= tolerance:
            row.append(entry)
        else:
            rows.append([entry])

    sorted_entries = []
    for row in rows:
        row.sort(key=lambda item: item["x"])
        sorted_entries.extend((item["box"], item["text"], item["confidence"]) for item in row)
    return sorted_entries


def _remove_repeated_page_lines(page_lines: list[list[str]]) -> tuple[list[list[str]], int]:
    if len(page_lines) < 2:
        return page_lines, 0

    line_pages = {}
    for page_index, lines in enumerate(page_lines):
        for line in set(lines):
            normalized = re.sub(r"\s+", "", line).lower()
            if len(normalized) < 8:
                continue
            line_pages.setdefault(normalized, set()).add(page_index)

    repeat_threshold = max(2, int(len(page_lines) * 0.6 + 0.5))
    repeated = {
        line
        for line, pages in line_pages.items()
        if len(pages) >= repeat_threshold
    }
    if not repeated:
        return page_lines, 0

    cleaned_pages = []
    removed_count = 0
    for lines in page_lines:
        cleaned = []
        for line in lines:
            normalized = re.sub(r"\s+", "", line).lower()
            if normalized in repeated:
                removed_count += 1
                continue
            cleaned.append(line)
        cleaned_pages.append(cleaned)
    return cleaned_pages, removed_count
