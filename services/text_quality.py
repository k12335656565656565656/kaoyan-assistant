import re


def clean_material_text(text):
    if not text:
        return ""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def analyze_text_quality(text, page_count=1, empty_page_count=0):
    cleaned = clean_material_text(text)
    compact = re.sub(r"\s+", "", cleaned)
    total_chars = len(compact)
    usable_chars = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9，。！？；：、（）《》“”‘’\-\+\*/=\.%,]", compact))
    garbled_chars = compact.count("�") + len(re.findall(r"[\ufffd□■◆�]", compact))
    usable_ratio = usable_chars / total_chars if total_chars else 0.0
    garbled_ratio = garbled_chars / total_chars if total_chars else 1.0
    avg_chars_per_page = total_chars / max(page_count, 1)

    warnings = []
    if total_chars < 80:
        warnings.append("提取文本过短")
    if avg_chars_per_page < 30 and page_count > 1:
        warnings.append("平均每页可读字符较少")
    if usable_ratio < 0.6:
        warnings.append("可读字符占比较低，可能存在乱码或扫描质量问题")
    if garbled_ratio > 0.1:
        warnings.append("疑似乱码字符占比较高")
    if empty_page_count and empty_page_count >= max(page_count // 2, 1):
        warnings.append("空白页较多，可能提取不完整")

    acceptable = (
        total_chars >= 80
        and usable_ratio >= 0.6
        and garbled_ratio <= 0.1
        and (page_count <= 1 or avg_chars_per_page >= 30)
        and empty_page_count < max(page_count // 2, 1)
    )

    confidence = 0.9
    if not acceptable:
        confidence = 0.35
    elif warnings:
        confidence = 0.65

    return {
        "cleaned_text": cleaned,
        "total_chars": total_chars,
        "avg_chars_per_page": avg_chars_per_page,
        "usable_ratio": usable_ratio,
        "garbled_ratio": garbled_ratio,
        "empty_page_count": empty_page_count,
        "acceptable": acceptable,
        "warnings": warnings,
        "confidence": confidence,
    }


def merge_pdf_risk_into_quality(quality, pdf_diagnostics=None):
    pdf_diagnostics = pdf_diagnostics or {}
    merged = dict(quality)
    warnings = list(merged.get("warnings") or [])

    if pdf_diagnostics.get("needs_ocr"):
        warnings.append("检测到图片主导且重复水印明显的 PDF，建议跳过文字层直提并直接 OCR。")
        for reason in pdf_diagnostics.get("reasons") or []:
            warnings.append(f"PDF 检测：{reason}")
        merged["acceptable"] = False
        merged["confidence"] = min(merged.get("confidence", 0.9), 0.3)

    merged["warnings"] = warnings
    merged["pdf_diagnostics"] = pdf_diagnostics
    return merged
