"""Adapter boundary for the existing knowledge-base question generator."""

from typing import Callable, Iterable, Protocol

from ..models import DiagnosisPlanItem, DiagnosisQuestionRequest


class QuestionGenerator(Protocol):
    def __call__(self, request: DiagnosisQuestionRequest):
        """Return a generated question for the request."""


def adapt_existing_review_generator(generate_review_questions):
    """Adapt app.py's existing knowledge-base generator without importing app.py."""

    def generate(request: DiagnosisQuestionRequest):
        return generate_review_questions(
            [
                {
                    "knowledge_id": request.knowledge_point_id,
                    "difficulty_tier": request.difficulty_tier,
                }
            ]
        )

    return generate


def generate_diagnosis_questions(
    generator: Callable[[DiagnosisQuestionRequest], object],
    plan: Iterable[DiagnosisPlanItem],
):
    results = []
    for item in plan:
        request = DiagnosisQuestionRequest(
            index=item.index,
            knowledge_point_id=item.knowledge_point_id,
            difficulty_tier=item.difficulty_tier,
            purpose="diagnosis",
        )
        results.append(generator(request))
    return results
