from pathlib import Path
import re

from schemas.material_schema import MaterialResult
from services.docx_text_service import extract_docx_text
from services.material_cleaner import MaterialCleanResult, clean_material_for_extraction
from services.pdf_text_service import extract_pdf_text, inspect_pdf_for_ocr
from services.pdf_outline_service import extract_syllabus_outline, looks_like_exam_syllabus
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
    pdf_outline_fn=None,
    pdf_ocr_available=False,
    pdf_text_progress_fn=None,
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

    if suffix == ".docx":
        if Path(file_name or "").name.startswith("~$"):
            raise ValueError("这是 Word 自动生成的临时文件，请选择不以“~$”开头的原文档。")
        raw_text, docx_report = extract_docx_text(file_bytes=file_bytes, file_path=file_path)
        clean_result = _prepare_extraction_text(raw_text)
        warnings = [
            (
                "已提取 Word 文档："
                f"{docx_report['paragraph_count']} 个段落、"
                f"{docx_report['table_row_count']} 行表格"
            )
        ] + list(clean_result.warnings)
        if len(clean_result.cleaned_text) < 80:
            warnings.append("Word 文档文字较短，请确认内容完整")
        return _build_material_result(
            source_type="docx",
            process_method="docx_text_extract",
            raw_text=raw_text,
            confidence=0.97 if clean_result.cleaned_text else 0.0,
            warnings=warnings,
            clean_result=clean_result,
            ocr_report=docx_report,
        )

    if suffix == ".pdf" and file_path:
        pdf_probe = inspect_pdf_for_ocr(file_path, progress_callback=pdf_text_progress_fn)
        probe_quality = merge_pdf_risk_into_quality(
            analyze_text_quality(
                pdf_probe["text"],
                page_count=max(pdf_probe.get("diagnostic_page_count") or len(pdf_probe.get("sampled_pages") or []), 1),
                empty_page_count=pdf_probe["empty_page_count"],
            ),
            pdf_probe.get("pdf_diagnostics"),
        )
        should_skip_full_extract = bool(probe_quality.get("pdf_diagnostics", {}).get("needs_ocr"))

        if should_skip_full_extract:
            pdf_data = pdf_probe
        else:
            pdf_data = extract_pdf_text(file_path, progress_callback=pdf_text_progress_fn)

        quality = merge_pdf_risk_into_quality(
            analyze_text_quality(
            pdf_data["text"],
            page_count=pdf_data["page_count"],
            empty_page_count=pdf_data["empty_page_count"],
            ),
            pdf_data.get("pdf_diagnostics"),
        )
        if quality["acceptable"]:
            if looks_like_exam_syllabus(quality["cleaned_text"]):
                syllabus_outline, syllabus_report = extract_syllabus_outline(
                    quality["cleaned_text"],
                    max_items=400,
                )
                if syllabus_outline:
                    clean_result = MaterialCleanResult(
                        cleaned_text=syllabus_outline,
                        original_text_length=len(syllabus_outline),
                        cleaned_text_length=len(syllabus_outline),
                        page_markers=len(re.findall(r"===\s*第\s*\d+\s*页\s*===", syllabus_outline)),
                    )
                    warnings = list(quality["warnings"]) + [
                        "检测到考试大纲，已读取完整层级并切换为知识点目录整理模式。",
                    ]
                    return _build_material_result(
                        source_type="pdf",
                        process_method="pdf_outline_ai",
                        raw_text=quality["cleaned_text"],
                        confidence=quality["confidence"],
                        warnings=warnings + clean_result.warnings,
                        clean_result=clean_result,
                        page_count=pdf_data["page_count"],
                        empty_page_count=pdf_data["empty_page_count"],
                        pdf_diagnostics=quality.get("pdf_diagnostics"),
                        ocr_report=syllabus_report,
                    )
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
        if pdf_ocr_available and pdf_outline_fn:
            warnings.append("PDF 直接提取质量较低，已切换为提纲抽样识别")
            outline_report = {}
            try:
                outline_output = pdf_outline_fn(file_path)
                if isinstance(outline_output, tuple):
                    raw_outline_text, outline_report = outline_output
                else:
                    raw_outline_text = outline_output
                clean_result = _prepare_extraction_text(raw_outline_text)
            except Exception as exc:
                warnings.append(f"提纲抽样识别失败：{exc}")
                raw_outline_text = ""
                clean_result = _prepare_extraction_text("")
            warnings.append("图片型 PDF 仅抽样识别目录/章节提纲；知识点由 AI 发散生成，必须结合教材人工核对。")
            return _build_material_result(
                source_type="pdf",
                process_method="pdf_outline_ai",
                raw_text=raw_outline_text,
                confidence=0.6 if clean_result.cleaned_text else 0.0,
                warnings=warnings + clean_result.warnings,
                clean_result=clean_result,
                page_count=pdf_data["page_count"],
                empty_page_count=pdf_data["empty_page_count"],
                pdf_diagnostics=quality.get("pdf_diagnostics"),
                ocr_report=outline_report,
            )

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
