"""Deterministic evidence scoring used before an LLM explains a diagnosis."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..models import ExamQuestion, MasteryEvidence, StudentProfile


@dataclass(frozen=True)
class WeightedKnowledgeEvidence:
    knowledge_point_id: str
    weighted_accuracy: float
    weakness_score: float
    question_count: int
    wrong_count: int
    feedback: str


def _feedback_factor(error_type: str) -> float:
    if "知识点遗漏" in error_type:
        return 1.25
    if "偏难" in error_type:
        return 1.1
    if "偏简单" in error_type:
        return 0.9
    return 1.0


def _question_weight(question: ExamQuestion) -> float:
    source_weight = 1.25 if question.mapping_status == "confirmed" else 1.0
    difficulty_weight = 1.0 + (1.0 - question.difficulty_coefficient) * 0.5
    return question.score * source_weight * difficulty_weight


def build_diagnosis_report(
    profile: StudentProfile,
    questions: Sequence[ExamQuestion],
    evidence: Iterable[MasteryEvidence],
) -> tuple[WeightedKnowledgeEvidence, ...]:
    del profile
    by_question = {question.question_id: question for question in questions}
    grouped = defaultdict(lambda: {"total": 0.0, "correct": 0.0, "weakness": 0.0, "count": 0, "wrong": 0, "feedback": []})
    for item in evidence:
        if not item.source.startswith("diagnosis") or item.question_id not in by_question:
            continue
        question = by_question[item.question_id]
        weight = _question_weight(question) * _feedback_factor(item.error_type)
        # Evidence is already split into one row per knowledge point when an
        # item has multiple tags. Attribute the row to its own tag once.
        knowledge_point_id = item.knowledge_point_id
        if knowledge_point_id not in question.knowledge_point_ids:
            continue
        for knowledge_point_id in (knowledge_point_id,):
            bucket = grouped[knowledge_point_id]
            bucket["total"] += weight
            bucket["correct"] += weight if item.is_correct else 0.0
            bucket["weakness"] += weight * (0 if item.is_correct else 1)
            bucket["count"] += 1
            bucket["wrong"] += int(not item.is_correct)
            if item.error_type:
                bucket["feedback"].append(item.error_type.replace("诊断答错；反馈: ", ""))
    report = [
        WeightedKnowledgeEvidence(
            knowledge_point_id=knowledge_point_id,
            weighted_accuracy=bucket["correct"] / bucket["total"] if bucket["total"] else 0.0,
            weakness_score=bucket["weakness"],
            question_count=bucket["count"],
            wrong_count=bucket["wrong"],
            feedback="；".join(dict.fromkeys(bucket["feedback"])),
        )
        for knowledge_point_id, bucket in grouped.items()
    ]
    return tuple(sorted(report, key=lambda item: (-item.weakness_score, item.knowledge_point_id)))


def build_diagnosis_summary_prompt(
    profile: StudentProfile,
    report: Sequence[WeightedKnowledgeEvidence],
) -> str:
    evidence_lines = "\n".join(
        f"- {item.knowledge_point_id}: 加权薄弱分 {item.weakness_score:.2f}，"
        f"加权正确率 {item.weighted_accuracy:.0%}，错 {item.wrong_count}/{item.question_count}，"
        f"主观反馈 {item.feedback or '无'}"
        for item in report
    ) or "- 无可用诊断证据"
    return f"""你是考研数学诊断助教。学生目标分 {profile.target_score:.0f}/150，当前分 {profile.current_score:.0f}/150。
以下是系统根据每题分值、难度、题源和学生反馈计算出的加权证据：
{evidence_lines}

只依据这些证据总结 3 到 5 条最值得优先处理的薄弱点，并分别说明错因和下一步练法。不得编造未出现的题目、知识点、分数或考试规律；加权薄弱分越高，优先级越高。"""
