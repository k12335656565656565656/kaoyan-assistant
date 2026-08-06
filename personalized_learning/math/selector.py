"""Select the next confirmed real question using explainable weights."""

from collections import Counter
from typing import Iterable, Mapping, Sequence

from ..models import DIFFICULTY_TIERS, ExamQuestion, MasterySnapshot, StudentProfile
from .requirements import target_mastery_for_tier


def _tier_weight(tier: str, target_ratio: float) -> float:
    return {
        "基础": 1.3 - 0.6 * target_ratio,
        "标准": 0.8 + 0.9 * target_ratio,
        "提高": 0.25 + 1.8 * target_ratio,
    }[tier]


def select_next_question(
    profile: StudentProfile,
    mastery_by_knowledge: Mapping[str, MasterySnapshot],
    eligible_questions: Iterable[ExamQuestion],
    recent_question_ids: Sequence[str] = (),
):
    questions = [
        question
        for question in eligible_questions
        if question.mapping_status == "confirmed" and question.question_id not in set(recent_question_ids)
    ]
    if not questions:
        return None
    knowledge_frequency = Counter(
        knowledge_point_id
        for question in questions
        for knowledge_point_id in question.knowledge_point_ids
    )
    target_ratio = profile.target_ratio
    max_year = max(question.year for question in questions)
    scored = []
    for question in questions:
        tier = question.difficulty_tier
        target_mastery = target_mastery_for_tier(tier, target_ratio)
        gaps = []
        risks = []
        importance = 0.0
        for knowledge_point_id in question.knowledge_point_ids:
            snapshot = mastery_by_knowledge.get(knowledge_point_id)
            mastery = snapshot.mastery if snapshot else 0.35
            gaps.append(max(0.05, target_mastery - mastery))
            risks.append(snapshot.forgetting_risk if snapshot else 0.0)
            importance += 1.0 + 0.25 * knowledge_frequency[knowledge_point_id]
        gap = sum(gaps) / len(gaps)
        forgetting_factor = 0.5 + 0.5 * (sum(risks) / len(risks))
        difficulty_weight = 0.7 + (1.0 - question.difficulty_coefficient)
        year_weight = 1.0 + 0.25 * max(0.0, question.year - (max_year - 10)) / 10.0
        score = (
            question.score
            * gap
            * forgetting_factor
            * difficulty_weight
            * importance
            * year_weight
            * _tier_weight(tier, target_ratio)
        )
        scored.append((score, question))
    scored.sort(key=lambda item: (-item[0], -item[1].year, item[1].question_id))
    return scored[0][1]
