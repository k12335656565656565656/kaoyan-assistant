from pathlib import Path

from schemas.material_schema import MaterialResult
from services.pdf_text_service import extract_pdf_text
from services.text_quality import analyze_text_quality, clean_material_text


def route_material_input(
    *,
    file_name=None,
    file_path=None,
    file_bytes=None,
    pasted_text=None,
    image_ocr_fn=None,
    pdf_ocr_fn=None,
    pdf_ocr_available=False,
):
    pasted_text = pasted_text or ""
    if pasted_text.strip():
        cleaned = clean_material_text(pasted_text)
        warnings = []
        if len(cleaned) < 80:
            warnings.append("粘贴文本较短，请确认内容完整")
        return MaterialResult(
            source_type="pasted_text",
            process_method="pasted_text",
            extracted_text=cleaned,
            confidence=0.98 if cleaned else 0.0,
            warnings=warnings,
        )

    suffix = Path(file_name or "").suffix.lower()
    if suffix == ".txt":
        decoded = ""
        if file_bytes:
            decoded = file_bytes.decode("utf-8", errors="ignore")
        cleaned = clean_material_text(decoded)
        warnings = ["当前输入来自 txt 文件，按直接文本处理"]
        if len(cleaned) < 80:
            warnings.append("文本较短，请确认内容完整")
        return MaterialResult(
            source_type="pasted_text",
            process_method="pasted_text",
            extracted_text=cleaned,
            confidence=0.95 if cleaned else 0.0,
            warnings=warnings,
        )

    if suffix == ".pdf" and file_path:
        pdf_data = extract_pdf_text(file_path)
        quality = analyze_text_quality(
            pdf_data["text"],
            page_count=pdf_data["page_count"],
            empty_page_count=pdf_data["empty_page_count"],
        )
        if quality["acceptable"]:
            return MaterialResult(
                source_type="pdf",
                process_method="pdf_text_extract",
                extracted_text=quality["cleaned_text"],
                confidence=quality["confidence"],
                warnings=quality["warnings"],
            )

        warnings = list(quality["warnings"])
        warnings.append("PDF 直接提取质量较低，尝试 OCR 回退")
        if pdf_ocr_available and pdf_ocr_fn:
            ocr_text = clean_material_text(pdf_ocr_fn(file_path))
            return MaterialResult(
                source_type="pdf",
                process_method="pdf_ocr",
                extracted_text=ocr_text,
                confidence=0.65 if ocr_text else 0.0,
                warnings=warnings,
            )

        warnings.append("OCR 服务不可用，已保留直接提取结果")
        return MaterialResult(
            source_type="pdf",
            process_method="pdf_text_extract",
            extracted_text=quality["cleaned_text"],
            confidence=quality["confidence"],
            warnings=warnings,
        )

    if suffix in {".png", ".jpg", ".jpeg"} and file_bytes and image_ocr_fn:
        extracted_text = clean_material_text(image_ocr_fn(file_bytes))
        warnings = []
        if len(extracted_text) < 40:
            warnings.append("图片 OCR 结果较短，请人工确认")
        return MaterialResult(
            source_type="image",
            process_method="image_ocr",
            extracted_text=extracted_text,
            confidence=0.75 if extracted_text else 0.0,
            warnings=warnings,
        )

    return MaterialResult(
        source_type="pasted_text",
        process_method="pasted_text",
        extracted_text="",
        confidence=0.0,
        warnings=["未识别到可处理的资料输入"],
    )
