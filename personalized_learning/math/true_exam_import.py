"""Staging helpers for importing screenshot-based public math exam questions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..models import classify_difficulty
from ..repository import import_exam_questions, refresh_provisional_question_mappings


@dataclass(frozen=True)
class ScreenshotTask:
    year: int
    exam_type: str
    page_path: Path

    @property
    def page_name(self) -> str:
        return self.page_path.name


def discover_screenshot_tasks(data_root: Path, year: int, exam_type: str):
    folder = Path(data_root) / str(year) / "screenshots" / exam_type
    if not folder.exists():
        return ()
    return tuple(
        ScreenshotTask(int(year), exam_type, path)
        for path in sorted(folder.glob("*.png"), key=lambda item: item.name)
    )


def build_extraction_prompt(exam_type: str, year: int, page_name: str, knowledge_catalog=()) -> str:
    catalog_lines = []
    for item in knowledge_catalog:
        if isinstance(item, dict):
            knowledge_id = str(item.get("id") or "").strip()
            label = str(item.get("name") or item.get("title") or "").strip()
            if not label:
                text = str(item.get("text") or "")
                label = next(
                    (line.lstrip("# ").strip() for line in text.splitlines() if line.strip()),
                    "",
                )
        else:
            knowledge_id = str(item or "").strip()
            label = ""
        if not knowledge_id:
            continue
        label = label or knowledge_id
        catalog_lines.append(f"- {knowledge_id}：{label}")
    catalog_text = "\n".join(catalog_lines) or "（未提供目录，暂留空数组）"
    return f"""你是考研数学真题资料整理员。请只识别图片中的 {year} 年 {exam_type} 真题及答案信息。
图片来源：{page_name}。
不得输出思考过程、解释性文字或 Markdown，只输出一个合法 JSON 对象。
若本页没有完整题目，输出 {{"questions": []}}。

JSON 格式：
{{"questions":[{{"question_no":"1","section":"选择题","score":4,"difficulty_coefficient":0.8,"question_text":"题干和选项","answer":"A","explanation":"解析","knowledge_point_ids":["001-知识点.md"]}}]}}

规则：题号、题干、答案、解析必须忠实于图片；难度系数范围为 (0,1]，越大表示越容易。
知识点标签必须由 Mimo 模型根据图片中的题目和下方目录判断，不能依靠题目文字的表面匹配，也不能由本地程序补全。
每道完整题目至少选择一个最相关的 knowledge_point_id；如果图片看不清、题目不完整或无法可靠判断，返回空数组，题目会进入待审核而不会进入诊断题池。
knowledge_point_ids 只能从下面目录中的 ID 选择，不能自造 ID。LaTeX 中的反斜杠必须在 JSON 字符串中写成双反斜杠，换行必须写成 \\n，不能输出原始控制字符。
可选知识点目录（ID：名称）：
{catalog_text}"""


def _json_payload(raw_text: str):
    raw_text = (raw_text or "").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    decoder = json.JSONDecoder()
    payload, end_index = decoder.raw_decode(raw_text)
    remainder = raw_text[end_index:].strip()
    if remainder and remainder.strip("}").strip():
        raise ValueError("unexpected content after JSON object")
    return payload


def _validate_question(row: dict, index: int):
    required = ("question_no", "section", "score", "difficulty_coefficient", "question_text", "answer")
    missing = [name for name in required if not str(row.get(name, "")).strip()]
    if missing:
        return f"question {index}: missing {', '.join(missing)}"
    try:
        score = float(row["score"])
        if score <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return f"question {index}: invalid score"
    try:
        classify_difficulty(float(row["difficulty_coefficient"]))
    except (TypeError, ValueError):
        return f"question {index}: invalid difficulty_coefficient"
    return ""


def _mimo_knowledge_point_ids(raw_values, knowledge_catalog=()):
    """Keep only labels explicitly returned by Mimo and known to the catalog."""
    if not isinstance(raw_values, list):
        return []
    candidates = []
    for value in raw_values:
        normalized = str(value or "").strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    catalog_ids = {
        str(item.get("id") or "").strip() if isinstance(item, dict) else str(item or "").strip()
        for item in knowledge_catalog
    }
    catalog_ids.discard("")
    if catalog_ids:
        return [value for value in candidates if value in catalog_ids]
    return candidates


def parse_extraction_response(raw_text: str, *, year: int, exam_type: str, page_name: str, knowledge_catalog=()):
    """Parse an LLM response into provisional rows without importing them yet."""
    try:
        payload = _json_payload(raw_text)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        return (), (f"invalid JSON: {error}",)
    rows = payload.get("questions", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return (), ("questions must be a list",)
    valid, errors = [], []
    for index, raw_row in enumerate(rows, start=1):
        if not isinstance(raw_row, dict):
            errors.append(f"question {index}: must be an object")
            continue
        error = _validate_question(raw_row, index)
        if error:
            errors.append(error)
            continue
        knowledge_ids = raw_row.get("knowledge_point_ids", [])
        if not isinstance(knowledge_ids, list):
            knowledge_ids = []
        question_text = str(raw_row["question_text"]).strip()
        explanation = str(raw_row.get("explanation", "")).strip()
        mapped_ids = _mimo_knowledge_point_ids(knowledge_ids, knowledge_catalog)
        valid.append(
            {
                "exam_type": exam_type,
                "year": int(year),
                "question_no": str(raw_row["question_no"]).strip(),
                "section": str(raw_row["section"]).strip(),
                "score": float(raw_row["score"]),
                "difficulty_coefficient": float(raw_row["difficulty_coefficient"]),
                "question_text": question_text,
                "answer": str(raw_row["answer"]).strip(),
                "explanation": explanation,
                "knowledge_point_ids": mapped_ids,
                "source_reference": f"{year}/{exam_type}/{page_name}",
                "mapping_status": "ai_suggested" if mapped_ids else "pending",
            }
        )
    return tuple(valid), tuple(errors)


def write_staging_batch(path: Path, rows: Iterable[dict], errors: Iterable[str] = ()):
    """Persist a reviewable batch before any database import."""
    payload = {"questions": list(rows), "errors": list(errors)}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_staged_import(
    data_root: Path,
    year: int,
    exam_type: str,
    response_dir: Path,
    staging_path: Path,
    connection,
    knowledge_catalog=(),
):
    """Import previously saved per-page Mimo JSON responses as provisional rows."""
    rows, errors = [], []
    response_dir = Path(response_dir)
    tasks = discover_screenshot_tasks(data_root, year, exam_type)
    for task in tasks:
        response_path = response_dir / task.page_path.with_suffix(".json").name
        if not response_path.exists():
            errors.append(f"{task.page_name}: response file is missing")
            continue
        parsed_rows, parsed_errors = parse_extraction_response(
            response_path.read_text(encoding="utf-8"),
            year=task.year,
            exam_type=task.exam_type,
            page_name=task.page_name,
            knowledge_catalog=knowledge_catalog,
        )
        rows.extend(parsed_rows)
        errors.extend(f"{task.page_name}: {error}" for error in parsed_errors)
    write_staging_batch(staging_path, rows, errors)
    data_version = f"{year}-screenshot-v1"
    result = import_exam_questions(
        connection,
        rows,
        data_version=data_version,
    ) if rows else {"imported": 0, "skipped": 0}
    mappings_updated = refresh_provisional_question_mappings(connection, rows, data_version) if rows else 0
    return {
        **result,
        "mappings_updated": mappings_updated,
        "pages": len(tasks),
        "errors": tuple(errors),
        "staging_path": Path(staging_path),
    }


def save_extraction_responses(
    tasks: Iterable[ScreenshotTask],
    response_dir: Path,
    extractor,
    force_page_names: Iterable[str] = (),
    knowledge_catalog=(),
    retry_unmapped: bool = False,
):
    """Call an injected image extractor once per screenshot and save raw output.

    Existing response files are kept so an interrupted paid extraction can resume.
    """
    response_dir = Path(response_dir)
    response_dir.mkdir(parents=True, exist_ok=True)
    force_names = frozenset(force_page_names)
    written = []
    for task in tasks:
        output_path = response_dir / task.page_path.with_suffix(".json").name
        if output_path.exists() and task.page_name not in force_names:
            if not retry_unmapped:
                written.append(output_path)
                continue
            try:
                cached_rows, cached_errors = parse_extraction_response(
                    output_path.read_text(encoding="utf-8"),
                    year=task.year,
                    exam_type=task.exam_type,
                    page_name=task.page_name,
                    knowledge_catalog=knowledge_catalog,
                )
            except (OSError, UnicodeError):
                cached_rows, cached_errors = (), ("cached response cannot be read",)
            needs_retry = bool(cached_errors) or any(row.get("mapping_status") == "pending" for row in cached_rows)
            if not needs_retry:
                written.append(output_path)
                continue
        raw_response = extractor(task, build_extraction_prompt(task.exam_type, task.year, task.page_name, knowledge_catalog))
        output_path.write_text(str(raw_response), encoding="utf-8")
        written.append(output_path)
    return tuple(written)
