from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

from services.material_router import route_material_input


def _normalize_tags(raw_tags) -> list[str]:
    if not raw_tags:
        return []
    if isinstance(raw_tags, str):
        raw_tags = raw_tags.replace("，", ",").replace("；", ",").replace("、", ",")
        return [item.strip() for item in raw_tags.split(",") if item.strip()]
    return [str(item).strip() for item in raw_tags if str(item).strip()]


def _build_chapter_name(chapter_name: str, filename: str, multi_file: bool) -> str:
    base = (chapter_name or "").strip()
    stem = Path(filename or "").stem
    if not base:
        return stem
    if multi_file:
        return f"{base} - {stem}"
    return base


def import_wrong_question_files(
    uploaded_files,
    *,
    subject: str,
    chapter_name: str,
    tags,
    image_ocr_fn,
    pdf_ocr_fn,
    pdf_ocr_available: bool,
) -> tuple[list[dict], list[str]]:
    drafts: list[dict] = []
    warnings: list[str] = []
    normalized_tags = _normalize_tags(tags)
    multi_file = len(uploaded_files or []) > 1

    for uploaded_file in uploaded_files or []:
        file_name = Path(uploaded_file.name).name
        suffix = Path(file_name).suffix.lower()
        file_bytes = uploaded_file.getvalue()
        file_path = ""
        temp_path = None

        try:
            if suffix == ".pdf":
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(file_bytes)
                    temp_path = Path(tmp.name)
                    file_path = str(temp_path)

            material_result = route_material_input(
                file_name=file_name,
                file_path=file_path,
                file_bytes=file_bytes,
                image_ocr_fn=image_ocr_fn,
                pdf_ocr_fn=pdf_ocr_fn,
                pdf_ocr_available=pdf_ocr_available if suffix == ".pdf" else False,
            )

            extracted_text = (material_result.extracted_text or "").strip()
            if not extracted_text:
                warnings.append(f"{file_name} 未提取到有效文本，请稍后手动补录。")

            drafts.append(
                {
                    "_draft_id": uuid4().hex,
                    "question": extracted_text or "",
                    "user_answer": "",
                    "correct_answer": "",
                    "explanation": "",
                    "subject": subject,
                    "chapter_name": _build_chapter_name(chapter_name, file_name, multi_file),
                    "source_text": material_result.raw_extracted_text or extracted_text,
                    "source_filename": file_name,
                    "source_file_type": suffix.lstrip("."),
                    "tags": list(normalized_tags),
                    "status": "active",
                    "warnings": list(material_result.warnings or []),
                }
            )
        except Exception as exc:
            warnings.append(f"{file_name} 识别失败：{exc}")
        finally:
            if temp_path:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    return drafts, warnings
