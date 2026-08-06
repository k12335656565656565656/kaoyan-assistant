"""Three-tier requirements derived from a profile and confirmed exam data."""

from collections import defaultdict
from typing import Iterable, Mapping

from ..models import (
    DIFFICULTY_TIERS,
    ExamQuestion,
    MasterySnapshot,
    PersonalizedRequirement,
    RequirementSummary,
    StudentProfile,
    clamp,
)


def _empty_snapshot(knowledge_point_id: str) -> MasterySnapshot:
    return MasterySnapshot(
        knowledge_point_id=knowledge_point_id,
        mastery=0.35,
        times_correct=0,
        times_wrong=0,
        recent_accuracy=0.0,
        stability_days=3.0,
        forgetting_risk=0.0,
    )


def target_mastery_for_tier(tier: str, target_ratio: float) -> float:
    values = {"基础": 0.78 + 0.12 * target_ratio, "标准": 0.62 + 0.23 * target_ratio, "提高": 0.42 + 0.33 * target_ratio}
    return clamp(values[tier])


def _year_importance(question: ExamQuestion, all_questions):
    years = [item.year for item in all_questions]
    span = max(1, max(years) - min(years))
    recency = 0.7 + 0.3 * ((question.year - min(years)) / span)
    return 1.0 + recency * 0.25


def build_requirements(
    profile: StudentProfile,
    mastery_by_knowledge: Mapping[str, MasterySnapshot],
    eligible_questions: Iterable[ExamQuestion],
    knowledge_point_ids: Iterable[str] = (),
):
    """Build weighted requirements and retain catalog points without mapped exams."""
    questions = [question for question in eligible_questions if question.mapping_status == "confirmed"]
    by_knowledge = defaultdict(list)
    for question in questions:
        for knowledge_point_id in question.knowledge_point_ids:
            by_knowledge[knowledge_point_id].append(question)

    target_ratio = profile.target_ratio
    requirements = {"必须掌握": [], "应该掌握": [], "冲刺掌握": []}
    priority_by_knowledge = {}
    for knowledge_point_id, knowledge_questions in by_knowledge.items():
        snapshot = mastery_by_knowledge.get(knowledge_point_id, _empty_snapshot(knowledge_point_id))
        for tier in DIFFICULTY_TIERS:
            tier_questions = [question for question in knowledge_questions if question.difficulty_tier == tier]
            if not tier_questions:
                continue
            if tier == "标准" and target_ratio < 0.35:
                continue
            if tier == "提高" and target_ratio < 0.65 and not profile.is_above_target:
                continue
            target_mastery = target_mastery_for_tier(tier, target_ratio)
            gap = max(0.0, target_mastery - snapshot.mastery)
            expected = sum(
                question.score * question.difficulty_coefficient / max(1, len(question.knowledge_point_ids))
                for question in tier_questions
            )
            importance = sum(_year_importance(question, questions) for question in tier_questions)
            forgetting_factor = 0.5 + 0.5 * snapshot.forgetting_risk
            priority = expected * gap * importance * forgetting_factor
            reason = (
                f"该知识点关联 {len(tier_questions)} 道已确认{tier}真题，"
                f"当前掌握度 {snapshot.mastery:.0%}，目标要求 {target_mastery:.0%}"
            )
            requirement = PersonalizedRequirement(
                knowledge_point_id=knowledge_point_id,
                tier=tier,
                mastery=snapshot.mastery,
                target_mastery=target_mastery,
                gap=gap,
                expected_contribution=expected,
                priority=priority,
                forgetting_risk=snapshot.forgetting_risk,
                reason=reason,
                related_question_ids=tuple(question.question_id for question in tier_questions),
                evidence_summary={
                    "times_correct": snapshot.times_correct,
                    "times_wrong": snapshot.times_wrong,
                    "recent_accuracy": snapshot.recent_accuracy,
                    "last_error_type": snapshot.last_error_type,
                },
            )
            requirements[{
                "基础": "必须掌握",
                "标准": "应该掌握",
                "提高": "冲刺掌握",
            }[tier]].append(requirement)
            priority_by_knowledge[knowledge_point_id] = max(
                priority_by_knowledge.get(knowledge_point_id, 0.0), priority
            )

    # A sparse confirmed bank must not make the rest of the math catalog vanish.
    # These entries have no score contribution until their exam mapping is reviewed,
    # but remain available for knowledge-base reinforcement and diagnosis follow-up.
    for knowledge_point_id in dict.fromkeys(str(value).strip() for value in knowledge_point_ids if str(value).strip()):
        if knowledge_point_id in by_knowledge:
            continue
        snapshot = mastery_by_knowledge.get(knowledge_point_id, _empty_snapshot(knowledge_point_id))
        if snapshot.mastery < 0.45 or snapshot.times_wrong > snapshot.times_correct:
            tier, group = "基础", "必须掌握"
        elif snapshot.mastery < 0.72:
            tier, group = "标准", "应该掌握"
        else:
            tier, group = "提高", "冲刺掌握"
        target_mastery = target_mastery_for_tier(tier, target_ratio)
        gap = max(0.0, target_mastery - snapshot.mastery)
        priority = gap * (1.0 + snapshot.times_wrong * 0.25) * (
            0.5 + 0.5 * snapshot.forgetting_risk
        )
        requirements[group].append(
            PersonalizedRequirement(
                knowledge_point_id=knowledge_point_id,
                tier=tier,
                mastery=snapshot.mastery,
                target_mastery=target_mastery,
                gap=gap,
                expected_contribution=0.0,
                priority=priority,
                forgetting_risk=snapshot.forgetting_risk,
                reason=(
                    f"该知识点暂未关联已确认真题，当前掌握度 {snapshot.mastery:.0%}，"
                    f"目标要求 {target_mastery:.0%}；题库映射待补"
                ),
                related_question_ids=(),
                evidence_summary={
                    "times_correct": snapshot.times_correct,
                    "times_wrong": snapshot.times_wrong,
                    "recent_accuracy": snapshot.recent_accuracy,
                    "last_error_type": snapshot.last_error_type,
                },
            )
        )
        priority_by_knowledge[knowledge_point_id] = priority

    for values in requirements.values():
        values.sort(key=lambda item: (-item.priority, item.knowledge_point_id, item.tier))
    mode = "巩固与冲刺" if profile.is_above_target else "建立目标基础"
    covered = min(150.0, sum(item.expected_contribution for values in requirements.values() for item in values))
    return RequirementSummary(
        must=tuple(requirements["必须掌握"]),
        should=tuple(requirements["应该掌握"]),
        stretch=tuple(requirements["冲刺掌握"]),
        expected_covered_score=covered,
        mode=mode,
        priority_by_knowledge=priority_by_knowledge,
    )


def build_diagnostic_requirements(
    profile: StudentProfile,
    mastery_by_knowledge: Mapping[str, MasterySnapshot],
    knowledge_point_ids: Iterable[str],
):
    """Create a first-phase plan before confirmed real-exam mappings exist."""
    target_mastery = 0.74 + 0.12 * profile.target_ratio
    requirements = {"必须掌握": [], "应该掌握": [], "冲刺掌握": []}
    priority_by_knowledge = {}
    for knowledge_point_id in dict.fromkeys(knowledge_point_ids):
        snapshot = mastery_by_knowledge.get(knowledge_point_id, _empty_snapshot(knowledge_point_id))
        gap = max(0.0, target_mastery - snapshot.mastery)
        if gap <= 0 and profile.target_ratio < 0.75:
            continue
        if snapshot.mastery < 0.45 or snapshot.times_wrong > snapshot.times_correct:
            tier = "基础"
            group = "必须掌握"
        elif gap > 0.12:
            tier = "标准"
            group = "应该掌握"
        else:
            tier = "提高"
            group = "冲刺掌握"
        priority = gap * (1.0 + snapshot.times_wrong * 0.25) * (
            0.5 + 0.5 * snapshot.forgetting_risk
        )
        requirement = PersonalizedRequirement(
            knowledge_point_id=knowledge_point_id,
            tier=tier,
            mastery=snapshot.mastery,
            target_mastery=target_mastery,
            gap=gap,
            expected_contribution=0.0,
            priority=priority,
            forgetting_risk=snapshot.forgetting_risk,
            reason=(
                f"诊断显示该知识点当前掌握度 {snapshot.mastery:.0%}，"
                f"目标要求 {target_mastery:.0%}，"
                f"错题 {snapshot.times_wrong} 次"
            ),
            evidence_summary={
                "times_correct": snapshot.times_correct,
                "times_wrong": snapshot.times_wrong,
                "recent_accuracy": snapshot.recent_accuracy,
                "last_error_type": snapshot.last_error_type,
            },
        )
        requirements[group].append(requirement)
        priority_by_knowledge[knowledge_point_id] = priority

    for values in requirements.values():
        values.sort(key=lambda item: (-item.priority, item.knowledge_point_id))
    return RequirementSummary(
        must=tuple(requirements["必须掌握"]),
        should=tuple(requirements["应该掌握"]),
        stretch=tuple(requirements["冲刺掌握"]),
        expected_covered_score=0.0,
        mode="巩固与冲刺" if profile.is_above_target else "建立目标基础",
        priority_by_knowledge=priority_by_knowledge,
    )
