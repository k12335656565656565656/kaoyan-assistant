from io import BytesIO
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


MAX_COMPRESSED_BYTES = 100 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_SINGLE_ENTRY_BYTES = 256 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250


def _load_docx_bytes(*, file_bytes=None, file_path=None):
    if file_bytes is not None:
        return bytes(file_bytes)
    if file_path:
        return Path(file_path).read_bytes()
    return b""


def _validate_docx_archive(payload):
    if not payload:
        raise ValueError("Word 文档为空，请重新选择文件。")
    if len(payload) > MAX_COMPRESSED_BYTES:
        raise ValueError("Word 文档超过 100MB，请拆分后重新上传。")

    try:
        with ZipFile(BytesIO(payload)) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if "word/document.xml" not in names:
                raise ValueError("文件不是有效的 DOCX 文档，请在 Word 中“另存为”DOCX 后重试。")

            total_uncompressed = 0
            for entry in entries:
                if entry.flag_bits & 0x1:
                    raise ValueError("暂不支持加密的 Word 文档，请取消密码保护后重试。")
                if entry.file_size > MAX_SINGLE_ENTRY_BYTES:
                    raise ValueError("Word 文档包含异常大的内部文件，请拆分或重新保存后重试。")
                total_uncompressed += entry.file_size
                if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                    raise ValueError("Word 文档解压后体积过大，请拆分后重新上传。")
                if entry.compress_size and entry.file_size / entry.compress_size > MAX_COMPRESSION_RATIO:
                    raise ValueError("Word 文档压缩结构异常，请重新保存后重试。")
    except BadZipFile as exc:
        raise ValueError("文件不是有效的 DOCX 文档，请在 Word 中“另存为”DOCX 后重试。") from exc


def _normalize_text(value):
    return re.sub(r"[ \t\u00a0]+", " ", str(value or "")).strip()


def _heading_level(paragraph):
    style = getattr(paragraph, "style", None)
    style_id = str(getattr(style, "style_id", "") or "")
    style_name = str(getattr(style, "name", "") or "")
    match = re.search(r"(?:Heading|标题)\s*([1-9])", f"{style_id} {style_name}", re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _is_list_paragraph(paragraph):
    style = getattr(paragraph, "style", None)
    style_text = (
        f"{getattr(style, 'style_id', '') or ''} "
        f"{getattr(style, 'name', '') or ''}"
    )
    if "list" in style_text.lower() or "列表" in style_text:
        return True
    properties = getattr(paragraph._p, "pPr", None)
    return bool(properties is not None and getattr(properties, "numPr", None) is not None)


def _iter_document_blocks(document):
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def extract_docx_text(*, file_bytes=None, file_path=None):
    payload = _load_docx_bytes(file_bytes=file_bytes, file_path=file_path)
    _validate_docx_archive(payload)

    try:
        document = Document(BytesIO(payload))
    except Exception as exc:
        raise ValueError("Word 文档无法解析，请在 Word 中重新保存为 DOCX 后重试。") from exc

    lines = []
    paragraph_count = 0
    heading_count = 0
    table_count = 0
    table_row_count = 0

    for block in _iter_document_blocks(document):
        if isinstance(block, Paragraph):
            text = _normalize_text(block.text)
            if not text:
                continue
            paragraph_count += 1
            level = _heading_level(block)
            if level:
                heading_count += 1
                lines.append(f"【{level}级标题】{text}")
            elif _is_list_paragraph(block):
                lines.append(f"- {text}")
            else:
                lines.append(text)
            continue

        table_count += 1
        for row in block.rows:
            cells = [_normalize_text(cell.text) for cell in row.cells]
            if not any(cells):
                continue
            table_row_count += 1
            lines.append(" | ".join(cells))

    text = "\n".join(lines).strip()
    if not text:
        raise ValueError("Word 文档没有可提取的文字；如果内容全部是扫描图片，请转成 PDF 后上传。")

    return text, {
        "paragraph_count": paragraph_count,
        "heading_count": heading_count,
        "table_count": table_count,
        "table_row_count": table_row_count,
        "text_length": len(text),
    }
