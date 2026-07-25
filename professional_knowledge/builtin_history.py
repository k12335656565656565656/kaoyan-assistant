"""Deployable built-in knowledge catalog for the 313 history examination."""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

from repositories.knowledge_repo import ensure_knowledge_schema, save_confirmed_knowledge_points


BUILTIN_HISTORY_SOURCE_TYPE = "builtin_history_313"
BUILTIN_HISTORY_PROCESS_METHOD = "builtin_history_catalog"
BUILTIN_HISTORY_SUBJECTS = {
    "历史学统考",
    "313历史学统考",
    "313 历史学统考",
    "313历史学基础",
    "313",
}
BUILTIN_HISTORY_EXAM_SUBJECTS = (
    "中国古代史",
    "中国近现代史",
    "世界古代中世纪史",
    "世界近现代史",
)
_DEFAULT_CATALOG_PATH = Path(__file__).with_name("builtin_history_points.json")


def is_history_subject(subject: str | None) -> bool:
    return str(subject or "").strip() in BUILTIN_HISTORY_SUBJECTS


def resolve_builtin_history_catalog_path(
    catalog_path: str | Path | None = None,
) -> Path:
    configured = catalog_path or os.environ.get("HISTORY_KNOWLEDGE_CATALOG", "")
    return Path(configured).expanduser() if configured else _DEFAULT_CATALOG_PATH


@lru_cache(maxsize=4)
def _load_catalog(path_value: str) -> tuple[dict, ...]:
    path = Path(path_value)
    if not path.is_file():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    points = payload.get("points") if isinstance(payload, dict) else None
    if not isinstance(points, list) or not points:
        raise RuntimeError("历史学统考内置知识库为空。")
    return tuple(dict(point) for point in points if isinstance(point, dict))


def load_builtin_history_points(
    catalog_path: str | Path | None = None,
) -> tuple[dict, ...]:
    path = resolve_builtin_history_catalog_path(catalog_path).resolve()
    return _load_catalog(str(path))


def ensure_builtin_history_points(
    conn,
    user_id: int,
    subject: str | None,
    *,
    catalog_path: str | Path | None = None,
) -> int:
    if not is_history_subject(subject):
        return 0
    target_subject = subject or "历史学统考"
    path = resolve_builtin_history_catalog_path(catalog_path)
    loaded_points = load_builtin_history_points(path)
    if not loaded_points:
        return 0
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    versioned_method = f"{BUILTIN_HISTORY_PROCESS_METHOD}:{content_hash[:12]}"
    points = [dict(point, subject=target_subject) for point in loaded_points]
    ensure_knowledge_schema(conn)
    existing, existing_method = conn.execute(
        """SELECT COUNT(*), COALESCE(MAX(process_method), '')
           FROM user_knowledge
           WHERE user_id=? AND subject=? AND source_type=?""",
        (user_id, target_subject, BUILTIN_HISTORY_SOURCE_TYPE),
    ).fetchone()
    if (
        existing == len(points)
        and existing_method == versioned_method
    ):
        return 0
    if existing:
        conn.execute(
            """DELETE FROM user_knowledge
               WHERE user_id=? AND subject=? AND source_type=?""",
            (user_id, target_subject, BUILTIN_HISTORY_SOURCE_TYPE),
        )
    return save_confirmed_knowledge_points(
        conn,
        user_id=user_id,
        points=points,
        material_meta={
            "subject": target_subject,
            "subject_key": "builtin_history_313",
            "chapter_name": "313历史学统考内置学习库",
            "material_filename": "313历史学统考内置学习库",
            "content_hash": content_hash,
            "source_type": BUILTIN_HISTORY_SOURCE_TYPE,
            "process_method": versioned_method,
        },
        strict=False,
        finalize_material=False,
    )
