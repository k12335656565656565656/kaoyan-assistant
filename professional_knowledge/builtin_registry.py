"""Registry for deployable built-in professional-course knowledge bases."""

from __future__ import annotations

from professional_knowledge.builtin_408 import (
    BUILTIN_408_SOURCE_TYPE,
    ensure_builtin_408_points,
    is_408_subject,
)
from professional_knowledge.builtin_history import (
    BUILTIN_HISTORY_SOURCE_TYPE,
    ensure_builtin_history_points,
    is_history_subject,
)


BUILTIN_SOURCE_TYPES = frozenset(
    {
        BUILTIN_408_SOURCE_TYPE,
        BUILTIN_HISTORY_SOURCE_TYPE,
    }
)

FIXED_SUBJECT_ALIASES = {
    "408综合": "408综合",
    "408": "408综合",
    "408计算机": "408综合",
    "计算机408": "408综合",
    "历史学统考": "历史学统考",
    "313历史学统考": "历史学统考",
    "313 历史学统考": "历史学统考",
    "313历史学基础": "历史学统考",
    "313": "历史学统考",
}


def canonical_fixed_subject(subject: str | None) -> str | None:
    return FIXED_SUBJECT_ALIASES.get(str(subject or "").strip())


def is_fixed_subject(subject: str | None) -> bool:
    return canonical_fixed_subject(subject) is not None


def is_builtin_source_type(source_type: str | None) -> bool:
    return str(source_type or "").strip() in BUILTIN_SOURCE_TYPES


def ensure_builtin_subject_points(conn, user_id: int, subject: str | None) -> int:
    if is_408_subject(subject):
        return ensure_builtin_408_points(conn, user_id, subject)
    if is_history_subject(subject):
        return ensure_builtin_history_points(conn, user_id, subject)
    return 0
