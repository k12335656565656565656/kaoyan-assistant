"""Turn one batch LLM response into traceable provisional diagnosis questions."""

from __future__ import annotations

import hashlib
import re
from typing import Iterable, Sequence

from ..models import DiagnosisPlanItem, ExamQuestion


TIER_COEFFICIENTS = {"基础": 0.8, "标准": 0.55, "提高": 0.3}


def build_variant_batch_prompt(
    plan: Sequence[DiagnosisPlanItem], reference_questions: Iterable[ExamQuestion]
) -> str:
    """Build one constrained request for all missing diagnostic slots."""
    references = tuple(reference_questions)
    references_text = "\n\n".join(
        f"参考真题 [{question.question_id}]\n知识点：{'、'.join(question.knowledge_point_ids)}\n"
        f"题干：{question.question_text}\n答案：{question.answer}\n解析：{question.explanation}"
        for question in references
    ) or "没有可用参考真题，只能依据指定知识点生成。"
    slots = "\n".join(
        f"{index + 1}. 知识点：{item.knowledge_point_id}；难度：{item.difficulty_tier}"
        for index, item in enumerate(plan)
    )
    return f"""你是考研数学题库编辑。基于给出的真题风格和知识点，生成共 {len(plan)} 道选择题变式题。
每一道题必须对应一个指定槽位，不能复述原题数字、条件或答案。不得输出思考过程、内心独白、标题或 Markdown 代码块。
数学公式只能使用 $...$ 或 $$...$$。

指定槽位：
{slots}

可参考的真题：
{references_text}

严格按以下格式连续输出，每道题结尾必须为 ---：
Q: 题干
A) 选项
B) 选项
C) 选项
D) 选项
ANSWER: 正确选项字母
EXPLAIN: 简洁解析
---"""


def _parse_blocks(raw_text: str):
    for block in re.split(r"(?m)^---\s*$", raw_text or ""):
        question_match = re.search(r"(?mi)^Q:\s*(.+?)(?=^ANSWER:|^EXPLAIN:|\Z)", block, re.DOTALL)
        answer_match = re.search(r"(?mi)^ANSWER:\s*([A-E])\b", block)
        explain_match = re.search(r"(?mi)^EXPLAIN:\s*(.+)\Z", block, re.DOTALL)
        if not question_match or not answer_match or not explain_match:
            continue
        question_text = question_match.group(1).strip()
        options = re.findall(r"(?mi)^\s*[A-E]\s*[).、].+$", question_text)
        if len(options) < 2:
            continue
        yield question_text, answer_match.group(1).upper(), explain_match.group(1).strip()


def _reference_for(item: DiagnosisPlanItem, references: Sequence[ExamQuestion]):
    related = [question for question in references if item.knowledge_point_id in question.knowledge_point_ids]
    return sorted(related or list(references), key=lambda question: (-question.year, question.question_id))[0] if references else None


def build_variant_questions(
    raw_text: str,
    plan: Sequence[DiagnosisPlanItem],
    reference_questions: Iterable[ExamQuestion],
    data_version: str = "generated-v1",
):
    """Create provisional question-bank records from a strict batched response."""
    references = tuple(reference_questions)
    variants = []
    for item, (question_text, answer, explanation) in zip(plan, _parse_blocks(raw_text)):
        reference = _reference_for(item, references)
        digest = hashlib.sha1(f"{item.knowledge_point_id}|{question_text}".encode("utf-8")).hexdigest()[:12]
        variants.append(
            ExamQuestion(
                question_id=f"variant:{digest}",
                exam_type=reference.exam_type if reference else "math1",
                year=reference.year if reference else 2026,
                question_no=f"variant-{item.index}-{digest[:6]}",
                section="AI 真题变式",
                score=reference.score if reference else 4,
                difficulty_coefficient=TIER_COEFFICIENTS[item.difficulty_tier],
                question_text=question_text,
                answer=answer,
                explanation=explanation,
                knowledge_point_ids=(item.knowledge_point_id,),
                source_reference=f"ai_variant:{reference.question_id if reference else 'knowledge_base'}",
                mapping_status="ai_suggested",
                data_version=data_version,
            )
        )
    return tuple(variants)
