"""Retrieve compact, traceable true-exam archetypes for question generation."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re

from professional_knowledge.builtin_408 import BUILTIN_408_SOURCE_TYPE
from professional_knowledge.builtin_history import BUILTIN_HISTORY_SOURCE_TYPE


_DATA_PATH = (
    Path(__file__).resolve().parents[1]
    / "professional_knowledge"
    / "true_exam_archetypes.json"
)
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,12}|[A-Za-z][A-Za-z0-9.+/_-]{1,20}")
_STOP_TOKENS = {
    "知识点",
    "核心内容",
    "考试",
    "真题",
    "专业课",
    "历史学",
    "计算机",
    "分析",
    "说明",
    "论述",
    "正确",
    "错误",
}


@lru_cache(maxsize=1)
def load_true_exam_archetypes() -> dict:
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise RuntimeError("真题范式库版本不受支持。")
    if not isinstance(payload.get("exams"), dict):
        raise RuntimeError("真题范式库缺少 exams。")
    return payload


def detect_exam_key(point: dict) -> str:
    text = " ".join(
        str(point.get(field) or "")
        for field in (
            "subject",
            "exam_subject",
            "chapter_name",
            "source_location",
            "knowledge_name",
            "core_definition",
            "keywords_json",
            "source_text",
        )
    )
    source_type = str(point.get("source_type") or "")
    if source_type == BUILTIN_408_SOURCE_TYPE or "408" in text:
        return "408"
    if source_type == BUILTIN_HISTORY_SOURCE_TYPE or "313" in text or "历史学统考" in text:
        return "313"
    if any(term in text for term in ("数据结构", "计算机组成原理", "操作系统", "计算机网络")):
        return "408"
    if any(term in text for term in ("中国古代史", "中国近现代史", "世界古代", "世界近现代")):
        return "313"
    return ""


def canonical_reference_mode(exam_key: str, mode: str) -> tuple[str, bool]:
    mode = str(mode or "quiz")
    if exam_key == "408":
        if mode == "choice":
            return "choice", False
        if mode in {"application", "algorithm", "quiz"}:
            return "application", False
        return ("choice" if mode == "blank" else "application"), True
    if exam_key == "313":
        if mode == "choice":
            return "choice", False
        if mode in {"application", "quiz"}:
            return "material", False
        if mode == "algorithm":
            return "essay", False
        return ("choice" if mode == "blank" else "essay"), True
    return mode, False


def select_true_exam_archetypes(
    point: dict,
    mode: str,
    *,
    variant: int = 1,
    limit: int = 3,
) -> list[dict]:
    exam_key = detect_exam_key(point)
    if not exam_key:
        return []
    payload = load_true_exam_archetypes()
    exam = payload["exams"].get(exam_key) or {}
    target_mode, _derived = canonical_reference_mode(exam_key, mode)
    point_text = _point_search_text(point)
    point_tokens = _tokens(point_text)
    point_subject = str(
        point.get("exam_subject")
        or point.get("chapter_name")
        or point.get("subject")
        or ""
    )

    ranked = []
    for index, item in enumerate(exam.get("archetypes") or []):
        if not isinstance(item, dict):
            continue
        item_mode = str(item.get("mode") or "")
        terms = set(_tokens(" ".join(str(term) for term in item.get("knowledge_terms") or [])))
        overlap = len(point_tokens & terms)
        subject = str(item.get("subject") or "")
        subject_match = int(bool(subject and subject in point_subject))
        text_match = int(bool(subject and subject in point_text))
        year = int(item.get("year") or 0)
        mode_match = int(item_mode == target_mode)
        score = (
            overlap * 14
            + mode_match * 45
            + subject_match * 8
            + text_match * 5
            + min(max(year - 2018, 0), 8)
        )
        ranked.append((score, overlap, year, -index, item))

    ranked.sort(reverse=True, key=lambda row: row[:4])
    if not ranked:
        return []
    requested_limit = max(1, int(limit or 1))
    rotation_seed = max(int(variant or 1) - 1, 0)
    same_mode = [row for row in ranked if str(row[4].get("mode") or "") == target_mode]
    cross_mode = [
        row
        for row in ranked
        if str(row[4].get("mode") or "") != target_mode and row[1] >= 2
    ]
    selected = _rotate_ranked(same_mode, rotation_seed)[:requested_limit]
    if cross_mode and requested_limit >= 2:
        cross = _rotate_ranked(cross_mode[:4], rotation_seed)[0]
        selected = selected[: requested_limit - 1] + [cross]
    elif len(selected) < requested_limit:
        selected.extend(
            row
            for row in _rotate_ranked(cross_mode, rotation_seed)
            if row not in selected
        )
    return [dict(row[4]) for row in selected[:requested_limit]]


def get_true_exam_reference_metadata(point: dict, mode: str, *, variant: int = 1) -> dict:
    exam_key = detect_exam_key(point)
    if not exam_key:
        return {
            "exam_key": "",
            "reference_ids": [],
            "derivation_type": "generic",
            "evidence_notice": "",
        }
    reference_mode, derived = canonical_reference_mode(exam_key, mode)
    items = select_true_exam_archetypes(point, mode, variant=variant)
    return {
        "exam_key": exam_key,
        "reference_mode": reference_mode,
        "reference_ids": [str(item.get("id") or "") for item in items if item.get("id")],
        "derivation_type": "true_exam_derived_review" if derived else "true_exam_archetype",
        "evidence_notice": (
            "该题型是基于真题知识点和设问结构派生的复习题，不是现行统考原生题型。"
            if derived
            else "该题借鉴本地真题的设问结构，不复制原题。"
        ),
    }


def build_true_exam_reference_block(point: dict, mode: str, *, variant: int = 1) -> str:
    exam_key = detect_exam_key(point)
    if not exam_key:
        return ""
    payload = load_true_exam_archetypes()
    exam = payload["exams"][exam_key]
    reference_mode, derived = canonical_reference_mode(exam_key, mode)
    items = select_true_exam_archetypes(point, mode, variant=variant)

    lines = [
        "【本地真题证据约束】",
        f"- 证据库：{exam.get('name')}；参考原生题型：{reference_mode}。",
        f"- 当前题型定位：{'真题派生复习题' if derived else '统考原生题型'}。",
        "- 只迁移设问骨架、材料密度、推理层次和评分方式；不得复制原题数据，不得声称新题来自某年真题。",
        "- 本地“答案解析”多为第三方资料，只能帮助识别答题层次，不能当作官方唯一措辞；题干事实优先于机构解析。",
    ]
    if derived:
        lines.append(
            "- 填空题/名词解释属于复习界面派生题型：必须从真题考过的稳定知识或能力点扣空/压缩，不得伪装成官方现行卷面题型。"
        )
    if items:
        lines.append("可迁移的相近真题范式：")
    for item in items:
        source = item.get("source") or {}
        source_label = (
            f"{item.get('year')}年题{item.get('question_no')}，"
            f"原生题型{item.get('mode')}，本地PDF第{source.get('page')}页，"
            f"证据等级{source.get('tier')}"
        )
        lines.append(
            f"- [{item.get('id')}] {source_label}："
            f"题干骨架={item.get('stem_pattern')}；"
            f"设问={_join(item.get('task_actions'))}；"
            f"答案组织={_join(item.get('answer_pattern'))}；"
            f"陷阱/区分度={_join(item.get('distractor_logic'))}。"
        )

    profile_rules = exam.get("quality_rules") or []
    if profile_rules:
        lines.append("由跨年真题归纳的硬规则：")
        lines.extend(f"- {rule}" for rule in profile_rules)

    trend_signals = exam.get("trend_signals") or []
    if trend_signals:
        lines.append("趋势线索（推断，不是真题事实）：")
        lines.extend(
            f"- {item.get('claim')}；依据：{item.get('evidence')}；置信度：{item.get('confidence')}。"
            for item in trend_signals[:3]
        )
    return "\n".join(lines)


def _point_search_text(point: dict) -> str:
    values = []
    for field in (
        "subject",
        "exam_subject",
        "chapter_name",
        "knowledge_name",
        "core_definition",
        "content",
        "review_content",
        "example_or_application",
        "keywords_json",
        "related_concepts_json",
        "pitfalls_json",
        "source_text",
    ):
        value = point.get(field)
        if isinstance(value, (list, tuple)):
            values.extend(str(item) for item in value)
        else:
            values.append(str(value or ""))
    return " ".join(values)


def _tokens(text: str) -> set[str]:
    tokens = set()
    for token in _TOKEN_RE.findall(str(text or "")):
        lowered = token.lower()
        if not lowered or lowered in _STOP_TOKENS:
            continue
        tokens.add(lowered)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            for width in (4, 3, 2):
                if len(token) < width:
                    continue
                tokens.update(
                    token[index : index + width]
                    for index in range(len(token) - width + 1)
                )
    return tokens


def _join(values) -> str:
    if not isinstance(values, list):
        return str(values or "无")
    return "、".join(str(value) for value in values if str(value).strip()) or "无"


def _rotate_ranked(rows: list[tuple], seed: int) -> list[tuple]:
    if not rows:
        return []
    pool_size = min(len(rows), 6)
    pool = list(rows[:pool_size])
    offset = seed % pool_size
    return pool[offset:] + pool[:offset] + list(rows[pool_size:])
