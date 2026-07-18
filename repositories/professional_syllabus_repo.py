from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _dump_json(value: Any) -> str:
    try:
        return json.dumps(value if value is not None else [], ensure_ascii=False)
    except (TypeError, ValueError):
        return "[]"


def _load_json(value: Any, default: Any = None) -> Any:
    if default is None:
        default = []
    if not value:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def ensure_professional_syllabus_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS professional_syllabus_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            source_ids_json TEXT NOT NULL DEFAULT '[]',
            source_signature TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            school_focus_json TEXT NOT NULL DEFAULT '[]',
            priority_points_json TEXT NOT NULL DEFAULT '[]',
            phase_plan_json TEXT NOT NULL DEFAULT '[]',
            raw_summary TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS ix_professional_syllabus_user_subject
           ON professional_syllabus_analysis(user_id, subject, updated_at DESC)"""
    )


def _row_to_dict(row: sqlite3.Row | None) -> dict:
    if row is None:
        return {}
    payload = dict(row)
    payload["source_ids"] = _load_json(payload.get("source_ids_json"), [])
    payload["school_focus"] = _load_json(payload.get("school_focus_json"), [])
    payload["priority_points"] = _load_json(payload.get("priority_points_json"), [])
    payload["phase_plan"] = _load_json(payload.get("phase_plan_json"), [])
    return payload


def create_syllabus_analysis(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    subject: str,
    source_ids: list[int],
) -> dict:
    ensure_professional_syllabus_schema(conn)
    now = _now()
    normalized_ids = sorted({int(item) for item in source_ids if str(item).strip()})
    source_signature = ",".join(str(item) for item in normalized_ids)
    cursor = conn.execute(
        """INSERT INTO professional_syllabus_analysis (
               user_id, subject, source_ids_json, source_signature, status,
               created_at, updated_at
           ) VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
        (user_id, subject, _dump_json(normalized_ids), source_signature, now, now),
    )
    return get_syllabus_analysis(conn, cursor.lastrowid)


def get_syllabus_analysis(conn: sqlite3.Connection, analysis_id: int) -> dict:
    ensure_professional_syllabus_schema(conn)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM professional_syllabus_analysis WHERE id=?",
        (analysis_id,),
    ).fetchone()
    return _row_to_dict(row)


def get_latest_syllabus_analysis(
    conn: sqlite3.Connection,
    user_id: int,
    subject: str,
) -> dict:
    ensure_professional_syllabus_schema(conn)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """SELECT * FROM professional_syllabus_analysis
           WHERE user_id=? AND subject=?
           ORDER BY id DESC
           LIMIT 1""",
        (user_id, subject),
    ).fetchone()
    return _row_to_dict(row)


def mark_syllabus_analysis_running(conn: sqlite3.Connection, analysis_id: int) -> None:
    ensure_professional_syllabus_schema(conn)
    conn.execute(
        """UPDATE professional_syllabus_analysis
           SET status='running', updated_at=?
           WHERE id=?""",
        (_now(), analysis_id),
    )


def save_syllabus_analysis_result(
    conn: sqlite3.Connection,
    analysis_id: int,
    *,
    school_focus: list[dict],
    priority_points: list[dict],
    phase_plan: list[dict],
    raw_summary: str = "",
) -> None:
    ensure_professional_syllabus_schema(conn)
    conn.execute(
        """UPDATE professional_syllabus_analysis
           SET status='completed',
               school_focus_json=?,
               priority_points_json=?,
               phase_plan_json=?,
               raw_summary=?,
               error_message='',
               updated_at=?
           WHERE id=?""",
        (
            _dump_json(school_focus),
            _dump_json(priority_points),
            _dump_json(phase_plan),
            raw_summary or "",
            _now(),
            analysis_id,
        ),
    )


def mark_syllabus_analysis_failed(
    conn: sqlite3.Connection,
    analysis_id: int,
    error_message: str,
) -> None:
    ensure_professional_syllabus_schema(conn)
    conn.execute(
        """UPDATE professional_syllabus_analysis
           SET status='failed', error_message=?, updated_at=?
           WHERE id=?""",
        (str(error_message or "")[:1000], _now(), analysis_id),
    )
