"""Select reusable, human-confirmed questions for a diagnosis session."""

from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple

from ..models import DiagnosisPlanItem, ExamQuestion


@dataclass(frozen=True)
class DiagnosisQuestionSelection:
    questions: Tuple[ExamQuestion, ...]
    uncovered_plan_indexes: Tuple[int, ...]
    uncovered_knowledge_point_ids: Tuple[str, ...] = ()


def variant_slots_to_generate(
    plan: Sequence[DiagnosisPlanItem],
    selection: DiagnosisQuestionSelection,
    true_question_ratio: float = None,
) -> Tuple[DiagnosisPlanItem, ...]:
    """Return plan slots needed to meet the requested AI-variant quota."""
    if len(selection.questions) >= len(plan):
        return ()
    if true_question_ratio is None:
        return ()
    desired_variants = len(plan) - round(len(plan) * true_question_ratio)
    selected_variants = sum(not question.is_true_exam for question in selection.questions)
    missing_count = max(0, desired_variants - selected_variants)
    return tuple(plan[:missing_count])


def diagnosis_generation_slots(
    plan: Sequence[DiagnosisPlanItem],
    selection: DiagnosisQuestionSelection,
    true_question_ratio: float = None,
) -> Tuple[DiagnosisPlanItem, ...]:
    """Return slots for optional generation only when the local batch is incomplete."""
    if len(selection.questions) >= len(plan):
        return ()

    uncovered = tuple(
        plan[index]
        for index in selection.uncovered_plan_indexes
        if 0 <= index < len(plan)
    )
    variant_slots = variant_slots_to_generate(plan, selection, true_question_ratio)
    return tuple(dict.fromkeys((*uncovered, *variant_slots)))


def _rank_candidates(candidates, previous_question_ids):
    previous = set(previous_question_ids)
    return sorted(
        candidates,
        key=lambda question: (
            question.question_id in previous,
            -question.year,
            str(question.question_no),
        ),
    )


def select_diagnosis_questions(
    plan: Sequence[DiagnosisPlanItem],
    questions: Iterable[ExamQuestion],
    prior_question_ids: Iterable[str] = (),
    allowed_mapping_statuses: Iterable[str] = ("confirmed",),
    true_question_ratio: float = None,
    coverage_knowledge_point_ids: Iterable[str] = (),
) -> DiagnosisQuestionSelection:
    """Map a diagnostic plan to reusable confirmed questions in the local bank.

    A question may be used again in a later diagnosis stage for the same user,
    but it is never duplicated inside one 20-question batch.
    """
    allowed_statuses = frozenset(allowed_mapping_statuses)
    eligible = tuple(
        question
        for question in questions
        if question.mapping_status in allowed_statuses and question.knowledge_point_ids
    )
    selected = []
    selected_ids = set()
    unmatched_items = []
    true_quota = round(len(plan) * true_question_ratio) if true_question_ratio is not None else None
    variant_quota = len(plan) - true_quota if true_quota is not None else None
    selected_true_years = set()
    prior_ids = set(prior_question_ids)
    coverage_ids = tuple(dict.fromkeys(
        str(value).strip() for value in coverage_knowledge_point_ids if str(value).strip()
    ))

    def choose_candidate(candidates, target_knowledge_point_ids=(), preferred_tier=None):
        if true_quota is None:
            desired_status = None
        else:
            true_count = sum(question.is_true_exam for question in selected)
            variant_count = len(selected) - true_count
            remaining_true = sum(question.is_true_exam for question in eligible if question.question_id not in selected_ids)
            remaining_variants = sum(not question.is_true_exam for question in eligible if question.question_id not in selected_ids)
            desired_status = None
            if true_count < true_quota and remaining_true >= true_quota - true_count:
                desired_status = "true_exam"
            elif variant_count < variant_quota and remaining_variants >= variant_quota - variant_count:
                desired_status = "ai_variant"
        target = set(target_knowledge_point_ids)
        ranked = sorted(
            candidates,
            key=lambda question: (
                -len(target.intersection(question.knowledge_point_ids)),
                question.difficulty_tier != preferred_tier if preferred_tier else False,
                question.is_true_exam != (desired_status == "true_exam") if desired_status else False,
                question.is_true_exam and question.year in selected_true_years,
                question.question_id in prior_ids,
                -question.year,
                str(question.question_no),
            ),
        )
        return ranked[0] if ranked else None

    if coverage_ids:
        covered_ids = set()
        for item in plan:
            candidate_pool = [question for question in eligible if question.question_id not in selected_ids]
            selected_question = choose_candidate(
                candidate_pool,
                target_knowledge_point_ids=set(coverage_ids) - covered_ids,
                preferred_tier=item.difficulty_tier,
            )
            if not selected_question:
                unmatched_items.append(item)
                continue
            selected.append(selected_question)
            selected_ids.add(selected_question.question_id)
            covered_ids.update(selected_question.knowledge_point_ids)
            if selected_question.is_true_exam:
                selected_true_years.add(selected_question.year)
    else:
        for item in plan:
            related = [
                question
                for question in eligible
                if item.knowledge_point_id in question.knowledge_point_ids
                and question.question_id not in selected_ids
            ]
            exact_tier = [question for question in related if question.difficulty_tier == item.difficulty_tier]
            candidate_pool = exact_tier or related
            selected_question = choose_candidate(candidate_pool)
            if not selected_question:
                unmatched_items.append(item)
                continue
            selected.append(selected_question)
            selected_ids.add(selected_question.question_id)
            if selected_question.is_true_exam:
                selected_true_years.add(selected_question.year)
    uncovered = []
    for item in unmatched_items:
        # A filler question can keep the batch at 20 items, but it cannot
        # claim that the planned knowledge point was actually covered.
        uncovered.append(item.index)
        fallback = choose_candidate(
            [question for question in eligible if question.question_id not in selected_ids]
        )
        if not fallback:
            continue
        selected.append(fallback)
        selected_ids.add(fallback.question_id)
    covered_ids = {tag for question in selected for tag in question.knowledge_point_ids}
    uncovered_knowledge = tuple(value for value in coverage_ids if value not in covered_ids)
    return DiagnosisQuestionSelection(tuple(selected), tuple(uncovered), uncovered_knowledge)
