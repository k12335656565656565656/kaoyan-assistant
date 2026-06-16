from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any


def _normalize_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        text = str(value).strip()
    except Exception:
        return default
    return text if text else default


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    try:
        text = str(value).strip().lower()
    except Exception:
        return default
    if text in {"true", "1", "yes", "y", "是"}:
        return True
    if text in {"false", "0", "no", "n", "否"}:
        return False
    return default


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        raw_items = (
            value.replace("；", ",")
            .replace("，", ",")
            .replace("、", ",")
            .replace("\n", ",")
            .split(",")
        )
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]

    normalized = []
    for item in raw_items:
        text = _normalize_text(item)
        if text:
            normalized.append(text)
    return normalized


@dataclass
class KnowledgePointDraft:
    knowledge_name: str = ""
    knowledge_type: str = ""
    subject: str = ""
    chapter_name: str = ""
    core_definition: str = ""
    exam_question_styles: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    related_concepts: list[str] = field(default_factory=list)
    pitfalls: list[str] = field(default_factory=list)
    example_or_application: str = ""
    review_priority: str = "中"
    source_text: str = ""
    source_page: str = ""
    source_location: str = ""
    tags: list[str] = field(default_factory=list)
    mastery_state: str = "待复习"
    is_ai_expansion: bool = False
    uncertainty_note: str = ""


@dataclass
class ConfirmedKnowledgePoint:
    knowledge_name: str = ""
    knowledge_type: str = ""
    subject: str = ""
    chapter_name: str = ""
    core_definition: str = ""
    exam_question_styles: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    related_concepts: list[str] = field(default_factory=list)
    pitfalls: list[str] = field(default_factory=list)
    example_or_application: str = ""
    review_priority: str = "中"
    source_text: str = ""
    source_page: str = ""
    source_location: str = ""
    tags: list[str] = field(default_factory=list)
    mastery_state: str = "待复习"
    is_ai_expansion: bool = False
    uncertainty_note: str = ""


def _normalize_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        return dict(raw)
    except Exception:
        return {}


def _build_knowledge_payload(raw: Any) -> dict[str, Any]:
    payload = _normalize_payload(raw)
    return {
        "knowledge_name": _normalize_text(payload.get("knowledge_name"), "未命名知识点"),
        "knowledge_type": _normalize_text(payload.get("knowledge_type")),
        "subject": _normalize_text(payload.get("subject")),
        "chapter_name": _normalize_text(payload.get("chapter_name")),
        "core_definition": _normalize_text(payload.get("core_definition")),
        "exam_question_styles": _normalize_list(payload.get("exam_question_styles")),
        "keywords": _normalize_list(payload.get("keywords")),
        "related_concepts": _normalize_list(payload.get("related_concepts")),
        "pitfalls": _normalize_list(payload.get("pitfalls")),
        "example_or_application": _normalize_text(payload.get("example_or_application")),
        "review_priority": _normalize_text(payload.get("review_priority"), "中"),
        "source_text": _normalize_text(payload.get("source_text")),
        "source_page": _normalize_text(payload.get("source_page")),
        "source_location": _normalize_text(payload.get("source_location")),
        "tags": _normalize_list(payload.get("tags")),
        "mastery_state": _normalize_text(payload.get("mastery_state"), "待复习"),
        "is_ai_expansion": _normalize_bool(payload.get("is_ai_expansion"), False),
        "uncertainty_note": _normalize_text(payload.get("uncertainty_note")),
    }


def normalize_knowledge_point_draft(raw: dict) -> KnowledgePointDraft:
    try:
        return KnowledgePointDraft(**_build_knowledge_payload(raw))
    except Exception:
        return KnowledgePointDraft()


def normalize_knowledge_point_drafts(raw_items: list) -> list[KnowledgePointDraft]:
    if not isinstance(raw_items, list):
        return []

    normalized = []
    for item in raw_items:
        normalized.append(normalize_knowledge_point_draft(item))
    return normalized


def knowledge_point_to_dict(point: Any) -> dict:
    if is_dataclass(point):
        return asdict(point)

    if isinstance(point, dict):
        normalized = normalize_knowledge_point_draft(point)
        return asdict(normalized)

    try:
        payload = {}
        for item in fields(KnowledgePointDraft):
            payload[item.name] = getattr(point, item.name, None)
        return asdict(normalize_knowledge_point_draft(payload))
    except Exception:
        return asdict(KnowledgePointDraft())


def validate_required_fields(point: Any) -> list[str]:
    warnings = []
    payload = knowledge_point_to_dict(point)

    if not _normalize_text(payload.get("knowledge_name")) or payload.get("knowledge_name") == "未命名知识点":
        warnings.append("knowledge_name 缺失或为默认值")
    if not _normalize_text(payload.get("source_text")):
        warnings.append("source_text 为空，建议补充原文依据")
    if not _normalize_text(payload.get("core_definition")):
        warnings.append("core_definition 为空")

    return warnings
