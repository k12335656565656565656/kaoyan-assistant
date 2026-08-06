"""SQLite persistence for math personalization without touching legacy tables."""

import csv
import json
import re
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .models import (
    ExamQuestion,
    MasteryEvidence,
    StudentProfile,
    ensure_datetime,
)


LEGACY_MATH_EXAM_TYPE_ALIASES = {
    "math1": "math1",
    "math2": "math2",
    "math3": "math3",
    "数一": "math1",
    "数一专属": "math1",
    "数二": "math2",
    "数二专属": "math2",
    "数三": "math3",
    "数三专属": "math3",
    "数学一": "math1",
    "数学二": "math2",
    "数学三": "math3",
    "数学一专属": "math1",
    "数学二专属": "math2",
    "数学三专属": "math3",
}


def normalize_math_exam_type(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    direct = LEGACY_MATH_EXAM_TYPE_ALIASES.get(raw)
    if direct:
        return direct

    compact = re.sub(r"[\s_-]+", "", raw).lower()
    if compact in {"math1", "math2", "math3"}:
        return compact

    match = re.fullmatch(r"(?:数学|数)([123一二三])(?:专属|专业)?", compact)
    if match:
        return {
            "1": "math1",
            "2": "math2",
            "3": "math3",
            "一": "math1",
            "二": "math2",
            "三": "math3",
        }[match.group(1)]
    return None


def get_legacy_math_exam_type(connection: sqlite3.Connection, user_id):
    """Read the original user portrait without requiring the app module."""
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(user_profiles)")}
    except sqlite3.DatabaseError:
        return None
    if "math_exam_type" not in columns:
        return None
    row = connection.execute(
        "SELECT math_exam_type FROM user_profiles WHERE user_id=?",
        (user_id,),
    ).fetchone()
    return normalize_math_exam_type(row[0] if row else None)


def _datetime_text(value: datetime) -> str:
    return ensure_datetime(value).isoformat()


def _parse_datetime(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS math_personalization_profiles (
            user_id TEXT PRIMARY KEY,
            subject_code TEXT NOT NULL,
            exam_type TEXT NOT NULL,
            target_score REAL NOT NULL,
            current_score REAL NOT NULL,
            score_source TEXT NOT NULL,
            target_school TEXT NOT NULL DEFAULT '',
            target_major TEXT NOT NULL DEFAULT '',
            undergraduate_major TEXT NOT NULL DEFAULT '',
            is_cross_exam INTEGER NOT NULL DEFAULT 0,
            current_stage TEXT NOT NULL DEFAULT '基础阶段',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS math_exam_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id TEXT NOT NULL,
            exam_type TEXT NOT NULL,
            year INTEGER NOT NULL,
            question_no TEXT NOT NULL,
            section TEXT NOT NULL,
            score REAL NOT NULL,
            difficulty_coefficient REAL NOT NULL,
            question_text TEXT NOT NULL,
            answer TEXT NOT NULL,
            explanation TEXT NOT NULL,
            knowledge_point_ids TEXT NOT NULL,
            source_reference TEXT NOT NULL,
            mapping_status TEXT NOT NULL,
            data_version TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            UNIQUE(exam_type, year, question_no, data_version)
        );
        CREATE TABLE IF NOT EXISTS math_mastery_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            knowledge_point_id TEXT NOT NULL,
            question_id TEXT NOT NULL,
            is_correct INTEGER NOT NULL,
            difficulty_coefficient REAL NOT NULL,
            error_type TEXT NOT NULL,
            answered_at TEXT NOT NULL,
            source TEXT NOT NULL,
            exam_type TEXT NOT NULL DEFAULT 'legacy'
        );
        CREATE INDEX IF NOT EXISTS ix_math_evidence_user_kp
            ON math_mastery_evidence(user_id, knowledge_point_id, answered_at);
        CREATE INDEX IF NOT EXISTS ix_math_exam_diagnostic_pool
            ON math_exam_questions(exam_type, mapping_status, year, question_no);
        """
    )
    evidence_columns = {row[1] for row in connection.execute("PRAGMA table_info(math_mastery_evidence)")}
    if "exam_type" not in evidence_columns:
        connection.execute(
            "ALTER TABLE math_mastery_evidence ADD COLUMN exam_type TEXT NOT NULL DEFAULT 'legacy'"
        )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(math_personalization_profiles)")}
    migrations = {
        "target_school": "TEXT NOT NULL DEFAULT ''",
        "target_major": "TEXT NOT NULL DEFAULT ''",
        "undergraduate_major": "TEXT NOT NULL DEFAULT ''",
        "is_cross_exam": "INTEGER NOT NULL DEFAULT 0",
        "current_stage": "TEXT NOT NULL DEFAULT '基础阶段'",
    }
    for name, definition in migrations.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE math_personalization_profiles ADD COLUMN {name} {definition}")
    connection.commit()


def repair_legacy_question_mapping_ids(
    connection: sqlite3.Connection,
    knowledge_point_ids: Sequence[str],
) -> int:
    """Repair legacy IDs whose Chinese filename suffix was replaced by question marks."""
    catalog_by_prefix = {}
    for knowledge_point_id in knowledge_point_ids:
        value = str(knowledge_point_id).strip()
        match = re.match(r"^(\d{3})-", value)
        if match:
            catalog_by_prefix.setdefault(match.group(1), []).append(value)

    replacement_by_legacy = {}
    for (raw_ids,) in connection.execute(
        "SELECT DISTINCT knowledge_point_ids FROM math_exam_questions WHERE knowledge_point_ids LIKE '%?%'"
    ):
        for legacy_id in json.loads(raw_ids or "[]"):
            if "?" not in legacy_id:
                continue
            match = re.match(r"^(\d{3})-", legacy_id)
            candidates = catalog_by_prefix.get(match.group(1), []) if match else []
            if len(candidates) == 1:
                replacement_by_legacy[legacy_id] = candidates[0]

    if not replacement_by_legacy:
        return 0

    repaired = 0
    for row_id, raw_ids in connection.execute(
        "SELECT id, knowledge_point_ids FROM math_exam_questions WHERE knowledge_point_ids LIKE '%?%'"
    ).fetchall():
        old_ids = tuple(json.loads(raw_ids or "[]"))
        new_ids = tuple(replacement_by_legacy.get(value, value) for value in old_ids)
        if new_ids == old_ids:
            continue
        connection.execute(
            "UPDATE math_exam_questions SET knowledge_point_ids=? WHERE id=?",
            (json.dumps(new_ids, ensure_ascii=False), row_id),
        )
        repaired += 1

    for legacy_id, canonical_id in replacement_by_legacy.items():
        connection.execute(
            "UPDATE math_mastery_evidence SET knowledge_point_id=? WHERE knowledge_point_id=?",
            (canonical_id, legacy_id),
        )
    connection.commit()
    return repaired


def _question_id(row: Mapping[str, object], data_version: str) -> str:
    explicit = str(row.get("question_id") or "").strip()
    if explicit:
        return explicit
    return f"{row['exam_type']}:{row['year']}:{row['question_no']}:{data_version}"


def _question_from_row(row, data_version: str, source_reference: str = "") -> ExamQuestion:
    if isinstance(row, ExamQuestion):
        if row.data_version == data_version and (not source_reference or row.source_reference == source_reference):
            return row
        return replace(
            row,
            data_version=data_version,
            source_reference=source_reference or row.source_reference,
        )
    row = dict(row)
    row["question_id"] = _question_id(row, data_version)
    row["data_version"] = data_version
    row["source_reference"] = row.get("source_reference") or source_reference
    row.setdefault("section", "")
    row.setdefault("answer", "")
    row.setdefault("explanation", "")
    row.setdefault("mapping_status", "pending")
    return ExamQuestion(**row)


def import_exam_questions(
    connection: sqlite3.Connection,
    rows: Iterable[object],
    data_version: str,
    source_reference: str = "",
):
    questions = [_question_from_row(row, data_version, source_reference) for row in rows]
    ensure_schema(connection)
    imported = 0
    skipped = 0
    try:
        for question in questions:
            cursor = connection.execute(
                """
                INSERT INTO math_exam_questions (
                    question_id, exam_type, year, question_no, section, score,
                    difficulty_coefficient, question_text, answer, explanation,
                    knowledge_point_ids, source_reference, mapping_status,
                    data_version, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exam_type, year, question_no, data_version) DO NOTHING
                """,
                (
                    question.question_id,
                    question.exam_type,
                    question.year,
                    question.question_no,
                    question.section,
                    question.score,
                    question.difficulty_coefficient,
                    question.question_text,
                    question.answer,
                    question.explanation,
                    json.dumps(question.knowledge_point_ids, ensure_ascii=False),
                    question.source_reference,
                    question.mapping_status,
                    question.data_version,
                    _datetime_text(datetime.now(timezone.utc)),
                ),
            )
            if cursor.rowcount:
                imported += 1
            else:
                skipped += 1
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {"imported": imported, "skipped": skipped}


def seed_question_bank_from_file(
    connection: sqlite3.Connection,
    path: Path,
):
    """Import a tracked question-bank JSON file without duplicating rows."""
    source_path = Path(path)
    if not source_path.exists():
        return {"imported": 0, "skipped": 0, "missing": True}

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or not isinstance(payload.get("questions"), list):
        raise ValueError(f"Invalid question bank format: {source_path}")

    exam_type = str(payload.get("exam_type") or "").strip()
    if not exam_type:
        raise ValueError(f"Question bank is missing exam_type: {source_path}")
    rows_by_version = {}
    for row in payload["questions"]:
        if not isinstance(row, Mapping) or str(row.get("exam_type") or "").strip() != exam_type:
            raise ValueError(f"Question bank contains an invalid exam_type: {source_path}")
        data_version = str(row.get("data_version") or "").strip()
        if not data_version:
            raise ValueError(f"Question bank row is missing data_version: {source_path}")
        rows_by_version.setdefault(data_version, []).append(row)

    imported = 0
    skipped = 0
    for data_version, rows in rows_by_version.items():
        result = import_exam_questions(connection, rows, data_version=data_version)
        imported += result["imported"]
        skipped += result["skipped"]
    return {"imported": imported, "skipped": skipped, "missing": False}


def refresh_provisional_question_mappings(
    connection: sqlite3.Connection,
    rows: Iterable[object],
    data_version: str,
) -> int:
    """Sync the latest Mimo mapping while preserving confirmed or manual tags."""
    ensure_schema(connection)
    updated = 0
    for row in rows:
        question = _question_from_row(row, data_version)
        if question.mapping_status == "confirmed":
            continue
        cursor = connection.execute(
            """UPDATE math_exam_questions
                  SET knowledge_point_ids=?, mapping_status=?
                WHERE exam_type=? AND year=? AND question_no=? AND data_version=?
                  AND mapping_status <> 'confirmed'""",
            (
                json.dumps(question.knowledge_point_ids, ensure_ascii=False),
                "ai_suggested" if question.knowledge_point_ids else "pending",
                question.exam_type,
                question.year,
                question.question_no,
                question.data_version,
            ),
        )
        updated += cursor.rowcount
    connection.commit()
    return updated


def confirm_question_mapping(
    connection: sqlite3.Connection,
    question_id: str,
    data_version: str,
    knowledge_point_ids: Sequence[str],
):
    """Apply the human-confirmed mapping without changing source question text."""
    normalized = tuple(dict.fromkeys(str(value).strip() for value in knowledge_point_ids if str(value).strip()))
    if not normalized:
        raise ValueError("confirmed mapping requires knowledge_point_ids")
    ensure_schema(connection)
    cursor = connection.execute(
        """UPDATE math_exam_questions
              SET knowledge_point_ids=?, mapping_status='confirmed'
            WHERE question_id=? AND data_version=?""",
        (json.dumps(normalized, ensure_ascii=False), question_id, data_version),
    )
    connection.commit()
    return cursor.rowcount == 1


def suggest_question_mapping(
    connection: sqlite3.Connection,
    question_id: str,
    data_version: str,
    knowledge_point_ids: Sequence[str],
):
    """Persist an AI-suggested mapping without promoting it to confirmed data."""
    normalized = tuple(dict.fromkeys(str(value).strip() for value in knowledge_point_ids if str(value).strip()))
    if not normalized:
        raise ValueError("suggested mapping requires knowledge_point_ids")
    ensure_schema(connection)
    cursor = connection.execute(
        """UPDATE math_exam_questions
              SET knowledge_point_ids=?, mapping_status='ai_suggested'
            WHERE question_id=? AND data_version=?""",
        (json.dumps(normalized, ensure_ascii=False), question_id, data_version),
    )
    connection.commit()
    return cursor.rowcount == 1


def _question_from_db(row) -> ExamQuestion:
    return ExamQuestion(
        question_id=row[0],
        exam_type=row[1],
        year=row[2],
        question_no=row[3],
        section=row[4],
        score=row[5],
        difficulty_coefficient=row[6],
        question_text=row[7],
        answer=row[8],
        explanation=row[9],
        knowledge_point_ids=tuple(json.loads(row[10] or "[]")),
        source_reference=row[11],
        mapping_status=row[12],
        data_version=row[13],
    )


def list_eligible_exam_questions(
    connection: sqlite3.Connection,
    exam_type: str,
    data_version: str = None,
):
    ensure_schema(connection)
    sql = """
        SELECT question_id, exam_type, year, question_no, section, score,
               difficulty_coefficient, question_text, answer, explanation,
               knowledge_point_ids, source_reference, mapping_status, data_version
          FROM math_exam_questions
         WHERE exam_type=? AND mapping_status='confirmed'
    """
    params = [exam_type]
    if data_version:
        sql += " AND data_version=?"
        params.append(data_version)
    sql += " ORDER BY year DESC, CAST(question_no AS INTEGER) ASC, question_no ASC"
    return [_question_from_db(row) for row in connection.execute(sql, params).fetchall()]


def list_diagnostic_questions(
    connection: sqlite3.Connection,
    exam_type: str,
    data_version: str = None,
):
    """Load confirmed true questions and provisional AI variants for diagnosis only.

    ``ai_suggested`` records never enter true-question weighting until a reviewer
    confirms their mapping; they merely let the diagnostic workflow be exercised
    while the bank is being built.
    """
    ensure_schema(connection)
    sql = """
        SELECT question_id, exam_type, year, question_no, section, score,
               difficulty_coefficient, question_text, answer, explanation,
               knowledge_point_ids, source_reference, mapping_status, data_version
          FROM math_exam_questions
         WHERE exam_type=? AND mapping_status IN ('confirmed', 'ai_suggested')
    """
    params = [exam_type]
    if data_version:
        sql += " AND data_version=?"
        params.append(data_version)
    sql += " ORDER BY year DESC, question_no ASC"
    return [_question_from_db(row) for row in connection.execute(sql, params).fetchall()]


def save_profile(connection: sqlite3.Connection, profile: StudentProfile) -> None:
    ensure_schema(connection)
    now = _datetime_text(datetime.now(timezone.utc))
    connection.execute(
        """
        INSERT INTO math_personalization_profiles (
            user_id, subject_code, exam_type, target_score, current_score,
            score_source, target_school, target_major, undergraduate_major,
            is_cross_exam, current_stage, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            subject_code=excluded.subject_code,
            exam_type=excluded.exam_type,
            target_score=excluded.target_score,
            current_score=excluded.current_score,
            score_source=excluded.score_source,
            target_school=excluded.target_school,
            target_major=excluded.target_major,
            undergraduate_major=excluded.undergraduate_major,
            is_cross_exam=excluded.is_cross_exam,
            current_stage=excluded.current_stage,
            updated_at=excluded.updated_at
        """,
        (
            profile.user_id,
            profile.subject_code,
            profile.exam_type,
            profile.target_score,
            profile.current_score,
            profile.score_source,
            profile.target_school,
            profile.target_major,
            profile.undergraduate_major,
            int(profile.is_cross_exam),
            profile.current_stage,
            now,
            now,
        ),
    )
    connection.commit()


def get_profile(connection: sqlite3.Connection, user_id: str):
    ensure_schema(connection)
    row = connection.execute(
        """SELECT user_id, subject_code, exam_type, target_score, current_score, score_source,
                  target_school, target_major, undergraduate_major, is_cross_exam, current_stage
             FROM math_personalization_profiles WHERE user_id=?""",
        (user_id,),
    ).fetchone()
    if not row:
        return None
    return StudentProfile(*row[:9], bool(row[9]), row[10])


def save_evidence(connection: sqlite3.Connection, evidence: MasteryEvidence) -> None:
    ensure_schema(connection)
    exam_type = str(evidence.exam_type or "").strip()
    if not exam_type:
        profile_row = connection.execute(
            "SELECT exam_type FROM math_personalization_profiles WHERE user_id=?",
            (evidence.user_id,),
        ).fetchone()
        exam_type = str(profile_row[0]).strip() if profile_row and profile_row[0] else "legacy"
    connection.execute(
        """
        INSERT INTO math_mastery_evidence (
            user_id, knowledge_point_id, question_id, is_correct,
            difficulty_coefficient, error_type, answered_at, source, exam_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evidence.user_id,
            evidence.knowledge_point_id,
            evidence.question_id,
            int(evidence.is_correct),
            evidence.difficulty_coefficient,
            evidence.error_type,
            _datetime_text(evidence.answered_at),
            evidence.source,
            exam_type,
        ),
    )
    connection.commit()


def list_evidence(connection: sqlite3.Connection, user_id: str, exam_type: str = None):
    ensure_schema(connection)
    sql = """SELECT user_id, knowledge_point_id, question_id, is_correct,
                     difficulty_coefficient, error_type, answered_at, source, exam_type
                FROM math_mastery_evidence WHERE user_id=?"""
    params = [user_id]
    if exam_type:
        sql += " AND exam_type=?"
        params.append(exam_type)
    sql += " ORDER BY answered_at ASC, id ASC"
    rows = connection.execute(sql, params).fetchall()
    return [
        MasteryEvidence(
            user_id=row[0],
            knowledge_point_id=row[1],
            question_id=row[2],
            is_correct=bool(row[3]),
            difficulty_coefficient=row[4],
            error_type=row[5],
            answered_at=_parse_datetime(row[6]),
            source=row[7],
            exam_type=row[8],
        )
        for row in rows
    ]


def get_mastery_snapshots(connection: sqlite3.Connection, user_id: str, exam_type: str = None):
    from .math.mastery import calculate_mastery

    return calculate_mastery(list_evidence(connection, user_id, exam_type))


def load_exam_question_rows(path: Path):
    """Load raw rows from JSON or CSV; validation happens during import."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("questions", [])
        if not isinstance(payload, list):
            raise ValueError("JSON question data must be a list or contain questions")
        return payload
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            raw_ids = row.get("knowledge_point_ids", "")
            try:
                row["knowledge_point_ids"] = json.loads(raw_ids) if raw_ids else []
            except json.JSONDecodeError:
                row["knowledge_point_ids"] = [part.strip() for part in raw_ids.split(";") if part.strip()]
        return rows
    raise ValueError("exam question data must be JSON or CSV")
