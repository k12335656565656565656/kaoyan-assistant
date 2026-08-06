"""Knowledge-base diagnosis planning and evidence creation."""

from datetime import datetime
from typing import Iterable, Sequence

from ..models import DiagnosisPlanItem, MasteryEvidence, classify_difficulty


def build_diagnosis_plan(
    knowledge_point_ids: Sequence[str], question_count: int = 20
):
    ids = tuple(dict.fromkeys(str(value).strip() for value in knowledge_point_ids if str(value).strip()))
    if not ids:
        raise ValueError("at least one knowledge point is required")
    if question_count <= 0:
        raise ValueError("question_count must be positive")

    basic_count = max(1, round(question_count * 0.4))
    standard_count = max(1, round(question_count * 0.4))
    tiers = (
        ["基础"] * basic_count
        + ["标准"] * standard_count
        + ["提高"] * max(1, question_count - basic_count - standard_count)
    )[:question_count]
    return [
        DiagnosisPlanItem(
            index=index,
            knowledge_point_id=ids[index % len(ids)],
            difficulty_tier=tier,
        )
        for index, tier in enumerate(tiers)
    ]


def has_completed_diagnosis(
    evidence: Iterable[MasteryEvidence], required_count: int = 20, session_id: str = ""
) -> bool:
    """Only unlock diagnosis conclusions after the full first batch is answered."""
    source = f"diagnosis:{session_id}" if session_id else "diagnosis"
    question_ids = {
        item.question_id
        for item in evidence
        if (item.source == source if session_id else item.source.startswith("diagnosis"))
        and str(item.question_id).strip()
    }
    return len(question_ids) >= required_count


def record_diagnosis_answer(
    user_id: str,
    question_id: str,
    knowledge_point_ids: Iterable[str],
    is_correct: bool,
    difficulty_coefficient: float,
    error_type: str = "",
    answered_at: datetime = None,
    session_id: str = "",
    exam_type: str = "",
):
    classify_difficulty(difficulty_coefficient)
    ids = tuple(dict.fromkeys(str(value).strip() for value in knowledge_point_ids if str(value).strip()))
    if not ids:
        raise ValueError("answer must reference at least one knowledge point")
    return [
        MasteryEvidence(
            user_id=user_id,
            knowledge_point_id=knowledge_point_id,
            question_id=question_id,
            is_correct=is_correct,
            difficulty_coefficient=difficulty_coefficient,
            error_type=error_type,
            answered_at=answered_at,
            source=f"diagnosis:{session_id}" if session_id else "diagnosis",
            exam_type=exam_type,
        )
        for knowledge_point_id in ids
    ]
