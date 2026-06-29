from pathlib import Path

from schemas.material_schema import MaterialResult
from services.material_cleaner import clean_material_for_extraction
from services.pdf_text_service import extract_pdf_text
from services.text_quality import analyze_text_quality, clean_material_text, merge_pdf_risk_into_quality


def _prepare_extraction_text(text):
    cleaned = clean_material_text(text)
    return clean_material_for_extraction(cleaned)


def _decode_text_bytes(file_bytes):
    if not file_bytes:
        return ""

    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="ignore")


def _build_material_result(
    *,
    source_type,
    process_method,
    raw_text,
    confidence,
    warnings,
    clean_result,
    page_count=0,
    empty_page_count=0,
    pdf_diagnostics=None,
    ocr_report=None,
):
    return MaterialResult(
        source_type=source_type,
        process_method=process_method,
        extracted_text=clean_result.cleaned_text,
        confidence=confidence,
        warnings=list(warnings or []),
        raw_extracted_text=raw_text or "",
        page_count=page_count or 0,
        empty_page_count=empty_page_count or 0,
        pdf_diagnostics=pdf_diagnostics or {},
        ocr_report=ocr_report or {},
        clean_report=clean_result.to_dict(),
    )


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
        clean_result = _prepare_extraction_text(pasted_text)
        warnings = list(clean_result.warnings)
        if len(clean_result.cleaned_text) < 80:
            warnings.append("粘贴文本较短，请确认内容完整")
        return _build_material_result(
            source_type="pasted_text",
            process_method="pasted_text",
            raw_text=pasted_text,
            confidence=0.98 if clean_result.cleaned_text else 0.0,
            warnings=warnings,
            clean_result=clean_result,
        )

    suffix = Path(file_name or "").suffix.lower()
    if suffix in {".txt", ".md"}:
        decoded = _decode_text_bytes(file_bytes)
        clean_result = _prepare_extraction_text(decoded)
        warnings = [f"当前输入来自 {suffix.lstrip('.')} 文件，按直接文本处理"] + list(clean_result.warnings)
        if len(clean_result.cleaned_text) < 80:
            warnings.append("文本较短，请确认内容完整")
        return _build_material_result(
            source_type="pasted_text",
            process_method="pasted_text",
            raw_text=decoded,
            confidence=0.95 if clean_result.cleaned_text else 0.0,
            warnings=warnings,
            clean_result=clean_result,
        )

    if suffix == ".pdf" and file_path:
        pdf_data = extract_pdf_text(file_path)
        quality = merge_pdf_risk_into_quality(
            analyze_text_quality(
            pdf_data["text"],
            page_count=pdf_data["page_count"],
            empty_page_count=pdf_data["empty_page_count"],
            ),
            pdf_data.get("pdf_diagnostics"),
        )
        if quality["acceptable"]:
            clean_result = _prepare_extraction_text(quality["cleaned_text"])
            return _build_material_result(
                source_type="pdf",
                process_method="pdf_text_extract",
                raw_text=quality["cleaned_text"],
                confidence=quality["confidence"],
                warnings=quality["warnings"] + clean_result.warnings,
                clean_result=clean_result,
                page_count=pdf_data["page_count"],
                empty_page_count=pdf_data["empty_page_count"],
                pdf_diagnostics=quality.get("pdf_diagnostics"),
            )

        warnings = list(quality["warnings"])
        warnings.append("PDF 直接提取质量较低，尝试 OCR 回退")
        if pdf_ocr_available and pdf_ocr_fn:
            ocr_report = {}
            try:
                ocr_output = pdf_ocr_fn(file_path)
                if isinstance(ocr_output, tuple):
                    raw_ocr_text, ocr_report = ocr_output
                else:
                    raw_ocr_text = ocr_output
                clean_result = _prepare_extraction_text(raw_ocr_text)
            except Exception as exc:
                warnings.append(f"OCR 回退失败：{exc}")
                raw_ocr_text = ""
                clean_result = _prepare_extraction_text("")
            return _build_material_result(
                source_type="pdf",
                process_method="pdf_ocr",
                raw_text=raw_ocr_text,
                confidence=0.65 if clean_result.cleaned_text else 0.0,
                warnings=warnings + clean_result.warnings,
                clean_result=clean_result,
                page_count=pdf_data["page_count"],
                empty_page_count=pdf_data["empty_page_count"],
                pdf_diagnostics=quality.get("pdf_diagnostics"),
                ocr_report=ocr_report,
            )

        warnings.append("OCR 服务不可用。文字型 PDF 仍可直接提取；扫描型 PDF 或图片可能无法识别。已保留直接提取结果。")
        clean_result = _prepare_extraction_text(quality["cleaned_text"])
        return _build_material_result(
            source_type="pdf",
            process_method="pdf_text_extract",
            raw_text=quality["cleaned_text"],
            confidence=quality["confidence"],
            warnings=warnings + clean_result.warnings,
            clean_result=clean_result,
            page_count=pdf_data["page_count"],
            empty_page_count=pdf_data["empty_page_count"],
            pdf_diagnostics=quality.get("pdf_diagnostics"),
        )

    if suffix in {".png", ".jpg", ".jpeg"} and file_bytes and image_ocr_fn:
        warnings = []
        try:
            raw_text = image_ocr_fn(file_bytes)
            clean_result = _prepare_extraction_text(raw_text)
        except Exception as exc:
            raw_text = ""
            clean_result = _prepare_extraction_text("")
            warnings.append(f"图片 OCR 失败：{exc}")
        if len(clean_result.cleaned_text) < 40:
            warnings.append("图片 OCR 结果较短，请人工确认")
        return _build_material_result(
            source_type="image",
            process_method="image_ocr",
            raw_text=raw_text,
            confidence=0.75 if clean_result.cleaned_text else 0.0,
            warnings=warnings + clean_result.warnings,
            clean_result=clean_result,
        )

    return _build_material_result(
        source_type="pasted_text",
        process_method="pasted_text",
        raw_text="",
        confidence=0.0,
        warnings=["未识别到可处理的资料输入"],
        clean_result=_prepare_extraction_text(""),
    )
