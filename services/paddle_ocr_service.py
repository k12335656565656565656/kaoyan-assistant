"""PaddleOCR-backed OCR helpers."""

from __future__ import annotations

import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any


# Work around a PaddlePaddle 3.3.x CPU oneDNN/PIR issue seen on Windows.
os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


class PaddleOCRUnavailable(RuntimeError):
    """Raised when PaddleOCR cannot be imported or initialized."""


@lru_cache(maxsize=2)
def _get_ocr(lang: str = "ch") -> Any:
    try:
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise PaddleOCRUnavailable(
            "PaddleOCR 未安装，请执行：python -m pip install paddleocr paddlepaddle"
        ) from exc

    try:
        return PaddleOCR(
            lang=lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except Exception as exc:
        raise PaddleOCRUnavailable(f"PaddleOCR 初始化失败：{exc}") from exc


def is_paddle_ocr_available(lang: str = "ch") -> bool:
    try:
        _get_ocr(lang)
        return True
    except Exception:
        return False


def _extract_texts_from_result(result: Any) -> list[str]:
    texts: list[str] = []

    if isinstance(result, dict):
        rec_texts = result.get("rec_texts")
        if isinstance(rec_texts, list):
            texts.extend(str(item).strip() for item in rec_texts if str(item).strip())
        return texts

    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                texts.extend(_extract_texts_from_result(item))
            elif isinstance(item, (list, tuple)):
                # Compatibility with older PaddleOCR result shape.
                for line in item:
                    if isinstance(line, (list, tuple)) and len(line) >= 2:
                        candidate = line[1]
                        if isinstance(candidate, (list, tuple)) and candidate:
                            text = str(candidate[0]).strip()
                            if text:
                                texts.append(text)
        return texts

    return texts


def extract_text_from_image_bytes(file_bytes: bytes, *, lang: str = "ch", suffix: str = ".png") -> str:
    if not file_bytes:
        return ""

    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        return extract_text_from_image_path(tmp_path, lang=lang)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def extract_text_from_image_path(image_path: str | Path, *, lang: str = "ch") -> str:
    ocr = _get_ocr(lang)
    try:
        result = ocr.predict(str(image_path))
    except Exception as exc:
        raise PaddleOCRUnavailable(f"PaddleOCR 识别失败：{exc}") from exc

    return "\n".join(_extract_texts_from_result(result)).strip()
