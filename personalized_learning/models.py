"""Data contracts for the personalized learning feature."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Mapping, Optional, Tuple


MAX_SCORE_BY_EXAM = {"math1": 150.0, "math2": 150.0, "math3": 150.0}
VALID_MAPPING_STATUSES = {"pending", "ai_suggested", "confirmed"}
VALID_SCORE_SOURCES = {"self_reported", "mock", "diagnostic"}
DIFFICULTY_TIERS = ("基础", "标准", "提高")


def classify_question_source(source_reference: str = "", mapping_status: str = "pending", section: str = "") -> str:
    """Infer source origin while keeping mapping review independent from it."""
    reference = str(source_reference or "").strip()
    section = str(section or "").strip()
    if reference.startswith("ai_variant:") or section.startswith("AI 真题变式"):
        return "ai_variant"
    if re.match(r"^(?:true_exam:)?\d{4}/math[123]/", reference) or mapping_status == "confirmed":
        return "true_exam"
    return "ai_variant"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_datetime(value: Optional[datetime]) -> datetime:
    if value is None:
        return utc_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def classify_difficulty(difficulty_coefficient: float) -> str:
    """Map an easiness coefficient to a training tier.

    The coefficient follows the exam convention: larger means easier.
    """
    coefficient = float(difficulty_coefficient)
    if not 0 < coefficient <= 1:
        raise ValueError("difficulty_coefficient must be in (0, 1]")
    if coefficient >= 0.65:
        return "基础"
    if coefficient >= 0.4:
        return "标准"
    return "提高"


def _knowledge_ids(values) -> Tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = [part.strip() for part in values.replace("；", ";").split(";")]
    cleaned = []
    for value in values:
        value = str(value).strip()
        if value and value not in cleaned:
            cleaned.append(value)
    return tuple(cleaned)


@dataclass(frozen=True)
class StudentProfile:
    user_id: str
    subject_code: str
    exam_type: str
    target_score: float
    current_score: float
    score_source: str
    target_school: str = ""
    target_major: str = ""
    undergraduate_major: str = ""
    is_cross_exam: bool = False
    current_stage: str = "基础阶段"

    def __post_init__(self):
        if not self.user_id:
            raise ValueError("user_id is required")
        if self.subject_code not in {"math", "english", "politics", "professional"}:
            raise ValueError("unsupported subject_code")
        if self.exam_type not in MAX_SCORE_BY_EXAM:
            raise ValueError("unsupported math exam_type")
        max_score = MAX_SCORE_BY_EXAM[self.exam_type]
        if not 0 <= float(self.target_score) <= max_score:
            raise ValueError(f"target_score must be between 0 and {int(max_score)}")
        if not 0 <= float(self.current_score) <= max_score:
            raise ValueError(f"current_score must be between 0 and {int(max_score)}")
        if self.score_source not in VALID_SCORE_SOURCES:
            raise ValueError("unsupported score_source")

    @property
    def target_ratio(self) -> float:
        return clamp(float(self.target_score) / MAX_SCORE_BY_EXAM[self.exam_type])

    @property
    def is_above_target(self) -> bool:
        return float(self.current_score) > float(self.target_score)


@dataclass(frozen=True)
class ExamQuestion:
    question_id: str
    exam_type: str
    year: int
    question_no: str
    section: str
    score: float
    difficulty_coefficient: float
    question_text: str
    answer: str
    explanation: str
    knowledge_point_ids: Tuple[str, ...] = field(default_factory=tuple)
    source_reference: str = ""
    mapping_status: str = "pending"
    data_version: str = "v1"

    def __post_init__(self):
        if not self.question_id:
            raise ValueError("question_id is required")
        if self.exam_type not in MAX_SCORE_BY_EXAM:
            raise ValueError("unsupported math exam_type")
        if int(self.year) < 1980:
            raise ValueError("year must be >= 1980")
        if not str(self.question_no).strip():
            raise ValueError("question_no is required")
        if float(self.score) <= 0:
            raise ValueError("score must be positive")
        classify_difficulty(self.difficulty_coefficient)
        if not str(self.question_text).strip():
            raise ValueError("question_text is required")
        if self.mapping_status not in VALID_MAPPING_STATUSES:
            raise ValueError("unsupported mapping_status")
        ids = _knowledge_ids(self.knowledge_point_ids)
        if self.mapping_status == "confirmed" and not ids:
            raise ValueError("confirmed question requires knowledge_point_ids")
        object.__setattr__(self, "knowledge_point_ids", ids)
        object.__setattr__(self, "year", int(self.year))
        object.__setattr__(self, "question_no", str(self.question_no).strip())
        object.__setattr__(self, "score", float(self.score))
        object.__setattr__(self, "difficulty_coefficient", float(self.difficulty_coefficient))

    @property
    def difficulty_tier(self) -> str:
        return classify_difficulty(self.difficulty_coefficient)

    @property
    def source_kind(self) -> str:
        return classify_question_source(self.source_reference, self.mapping_status, self.section)

    @property
    def is_true_exam(self) -> bool:
        return self.source_kind == "true_exam"


@dataclass(frozen=True)
class MasteryEvidence:
    user_id: str
    knowledge_point_id: str
    question_id: str
    is_correct: bool
    difficulty_coefficient: float
    error_type: str = ""
    answered_at: datetime = field(default_factory=utc_now)
    source: str = "diagnosis"
    exam_type: str = ""

    def __post_init__(self):
        if not self.user_id or not self.knowledge_point_id or not self.question_id:
            raise ValueError("user_id, knowledge_point_id and question_id are required")
        classify_difficulty(self.difficulty_coefficient)
        object.__setattr__(self, "answered_at", ensure_datetime(self.answered_at))
        object.__setattr__(self, "is_correct", bool(self.is_correct))


@dataclass(frozen=True)
class MasterySnapshot:
    knowledge_point_id: str
    mastery: float
    times_correct: int
    times_wrong: int
    recent_accuracy: float
    stability_days: float
    forgetting_risk: float
    last_answered_at: Optional[datetime] = None
    last_error_type: str = ""


@dataclass(frozen=True)
class DiagnosisPlanItem:
    index: int
    knowledge_point_id: str
    difficulty_tier: str
    purpose: str = "diagnosis"


@dataclass(frozen=True)
class DiagnosisQuestionRequest:
    index: int
    knowledge_point_id: str
    difficulty_tier: str
    purpose: str = "diagnosis"


@dataclass(frozen=True)
class PersonalizedRequirement:
    knowledge_point_id: str
    tier: str
    mastery: float
    target_mastery: float
    gap: float
    expected_contribution: float
    priority: float
    forgetting_risk: float
    reason: str
    related_question_ids: Tuple[str, ...] = field(default_factory=tuple)
    evidence_summary: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RequirementSummary:
    must: Tuple[PersonalizedRequirement, ...]
    should: Tuple[PersonalizedRequirement, ...]
    stretch: Tuple[PersonalizedRequirement, ...]
    expected_covered_score: float
    mode: str
    priority_by_knowledge: Mapping[str, float]


@dataclass(frozen=True)
class TrainingMaterialRequest:
    knowledge_point_id: str
    tier: str
    title: str
    focus: Tuple[str, ...]
    evidence_summary: Mapping[str, object]
    expected_contribution: float
