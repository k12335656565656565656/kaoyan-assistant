import hashlib
import json
import sqlite3
import unicodedata
from datetime import datetime
from typing import Any

from schemas.knowledge_schema import knowledge_point_to_dict, validate_required_fields


STRUCTURED_COLUMNS = {
    "knowledge_type": "TEXT",
    "core_definition": "TEXT",
    "exam_question_styles_json": "TEXT",
    "keywords_json": "TEXT",
    "related_concepts_json": "TEXT",
    "pitfalls_json": "TEXT",
    "example_or_application": "TEXT",
    "review_priority": "TEXT",
    "source_text": "TEXT",
    "source_page": "TEXT",
    "source_location": "TEXT",
    "tags_json": "TEXT",
    "mastery_state": "TEXT",
    "is_ai_expansion": "INTEGER",
    "uncertainty_note": "TEXT",
    "raw_json": "TEXT",
    "source_type": "TEXT",
    "process_method": "TEXT",
    "material_filename": "TEXT",
    "subject_key": "TEXT",
    "ingest_key": "TEXT",
    "status": "TEXT",
    "review_content": "TEXT",
    "review_generated_at": "TEXT",
    "updated_at": "TEXT",
}


def ensure_user_knowledge_structured_columns(conn):
    c = conn.cursor()
    existing_columns = {row[1] for row in c.execute("PRAGMA table_info(user_knowledge)").fetchall()}
    for column_name, column_type in STRUCTURED_COLUMNS.items():
        if column_name not in existing_columns:
            c.execute(f"ALTER TABLE user_knowledge ADD COLUMN {column_name} {column_type}")

    if "created_at" not in existing_columns:
        c.execute("ALTER TABLE user_knowledge ADD COLUMN created_at TEXT")


def ensure_knowledge_schema(conn):
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS user_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            material_id INTEGER,
            subject TEXT,
            chapter_name TEXT,
            knowledge_name TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    ensure_user_knowledge_structured_columns(conn)
    try:
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS ux_user_knowledge_user_ingest_key
               ON user_knowledge(user_id, ingest_key)"""
        )
    except sqlite3.IntegrityError:
        # A partially migrated database may already contain repeated non-null keys.
        # Keep every knowledge row and clear only the conflicting derived keys.
        conn.execute(
            """UPDATE user_knowledge
               SET ingest_key=NULL
               WHERE ingest_key IS NOT NULL
                 AND rowid NOT IN (
                     SELECT MIN(rowid)
                     FROM user_knowledge
                     WHERE ingest_key IS NOT NULL
                     GROUP BY user_id, ingest_key
                 )"""
        )
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS ux_user_knowledge_user_ingest_key
               ON user_knowledge(user_id, ingest_key)"""
        )


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _list_json(value):
    try:
        return json.dumps(value or [], ensure_ascii=False)
    except Exception:
        return "[]"


def _build_legacy_content(point_dict):
    lines = []
    if point_dict.get("knowledge_type"):
        lines.append(f"知识点类型：{point_dict.get('knowledge_type')}")
    if point_dict.get("core_definition"):
        lines.append(f"核心定义：{point_dict.get('core_definition')}")
    if point_dict.get("exam_question_styles"):
        lines.append(f"常见考法：{', '.join(point_dict.get('exam_question_styles') or [])}")
    if point_dict.get("keywords"):
        lines.append(f"关键词：{', '.join(point_dict.get('keywords') or [])}")
    if point_dict.get("pitfalls"):
        lines.append(f"易错点：{', '.join(point_dict.get('pitfalls') or [])}")
    if point_dict.get("source_text"):
        lines.append(f"原文依据：{point_dict.get('source_text')}")
    if not lines:
        lines.append(point_dict.get("core_definition") or "暂无摘要")
    return "\n".join(lines)


def _normalize_ingest_value(value: Any):
    if isinstance(value, dict):
        return {
            str(key): _normalize_ingest_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set)):
        normalized_items = [_normalize_ingest_value(item) for item in value]
        return sorted(
            normalized_items,
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
        )
    if isinstance(value, str):
        return " ".join(unicodedata.normalize("NFKC", value).split())
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return " ".join(unicodedata.normalize("NFKC", str(value)).split())


def _build_ingest_key(material_meta: dict, point_dict: dict) -> str:
    material_id = material_meta.get("material_id")
    if material_id is not None and str(material_id).strip():
        material_scope = {"material_id": str(material_id).strip()}
    else:
        material_scope = {
            "subject_key": material_meta.get("subject_key", ""),
            "subject": material_meta.get("subject", ""),
            "chapter_name": material_meta.get("chapter_name", ""),
            "material_filename": material_meta.get("material_filename", ""),
            "content_hash": material_meta.get("content_hash", ""),
        }
    payload = {
        "material_scope": _normalize_ingest_value(material_scope),
        "knowledge_point": _normalize_ingest_value(point_dict),
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _point_subject_key(point: Any) -> str:
    if isinstance(point, dict):
        return str(point.get("subject_key") or "").strip()
    return str(getattr(point, "subject_key", "") or "").strip()


def _sync_material_knowledge_count(
    conn,
    user_id: int,
    material_id: int,
    *,
    finalize_material: bool,
) -> None:
    if not _table_exists(conn, "user_materials"):
        return
    material_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(user_materials)").fetchall()
    }
    if not {"id", "knowledge_count", "processing_status"}.issubset(
        material_columns
    ):
        return

    knowledge_count = conn.execute(
        """SELECT COUNT(*) FROM user_knowledge
           WHERE user_id=? AND material_id=?""",
        (user_id, material_id),
    ).fetchone()[0]
    if "user_id" in material_columns:
        if finalize_material:
            conn.execute(
                """UPDATE user_materials
                   SET processing_status='done', knowledge_count=?
                   WHERE id=? AND user_id=?""",
                (knowledge_count, material_id, user_id),
            )
        else:
            conn.execute(
                """UPDATE user_materials
                   SET knowledge_count=?
                   WHERE id=? AND user_id=?""",
                (knowledge_count, material_id, user_id),
            )
    else:
        if finalize_material:
            conn.execute(
                """UPDATE user_materials
                   SET processing_status='done', knowledge_count=?
                   WHERE id=?""",
                (knowledge_count, material_id),
            )
        else:
            conn.execute(
                "UPDATE user_materials SET knowledge_count=? WHERE id=?",
                (knowledge_count, material_id),
            )


def save_confirmed_knowledge_points(
    conn,
    user_id,
    points,
    material_meta=None,
    *,
    strict=False,
    finalize_material=True,
) -> int:
    ensure_knowledge_schema(conn)
    material_meta = material_meta or {}
    points = list(points or [])
    if strict:
        invalid = []
        for index, point in enumerate(points, start=1):
            warnings = validate_required_fields(point)
            if warnings:
                invalid.append((index, warnings))
        if invalid:
            details = "；".join(
                f"第{index}条：{','.join(warnings)}"
                for index, warnings in invalid[:5]
            )
            raise ValueError(f"存在不完整的确认知识点，已拒绝入库：{details}")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c = conn.cursor()
    saved_count = 0

    for point in points or []:
        point_dict = knowledge_point_to_dict(point)
        subject = point_dict.get("subject") or material_meta.get("subject", "")
        chapter_name = point_dict.get("chapter_name") or material_meta.get(
            "chapter_name", ""
        )
        subject_key = _point_subject_key(point) or material_meta.get(
            "subject_key", ""
        )
        normalized_point = dict(point_dict)
        normalized_point["subject"] = subject
        normalized_point["chapter_name"] = chapter_name
        normalized_point["subject_key"] = subject_key
        ingest_key = _build_ingest_key(material_meta, normalized_point)
        content = _build_legacy_content(point_dict)
        raw_json = json.dumps(point_dict, ensure_ascii=False)

        c.execute(
            """INSERT OR IGNORE INTO user_knowledge (
                user_id, material_id, subject, subject_key, chapter_name,
                knowledge_name, content, ingest_key,
                knowledge_type, core_definition, exam_question_styles_json, keywords_json,
                related_concepts_json, pitfalls_json, example_or_application, review_priority,
                source_text, source_page, source_location, tags_json, mastery_state,
                is_ai_expansion, uncertainty_note, raw_json, source_type, process_method,
                material_filename, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                material_meta.get("material_id"),
                subject,
                subject_key,
                chapter_name,
                point_dict.get("knowledge_name", ""),
                content,
                ingest_key,
                point_dict.get("knowledge_type", ""),
                point_dict.get("core_definition", ""),
                _list_json(point_dict.get("exam_question_styles")),
                _list_json(point_dict.get("keywords")),
                _list_json(point_dict.get("related_concepts")),
                _list_json(point_dict.get("pitfalls")),
                point_dict.get("example_or_application", ""),
                point_dict.get("review_priority", ""),
                point_dict.get("source_text", ""),
                point_dict.get("source_page", ""),
                point_dict.get("source_location", ""),
                _list_json(point_dict.get("tags")),
                point_dict.get("mastery_state", ""),
                1 if point_dict.get("is_ai_expansion") else 0,
                point_dict.get("uncertainty_note", ""),
                raw_json,
                material_meta.get("source_type", ""),
                material_meta.get("process_method", ""),
                material_meta.get("material_filename", ""),
                "confirmed",
                now_str,
                now_str,
            ),
        )
        if c.rowcount > 0:
            saved_count += 1

    material_id = material_meta.get("material_id")
    if points and material_id is not None:
        _sync_material_knowledge_count(
            conn,
            user_id,
            material_id,
            finalize_material=bool(finalize_material),
        )

    return saved_count


def list_user_knowledge_points(conn, user_id, limit=100):
    ensure_knowledge_schema(conn)
    conn.row_factory = None
    c = conn.cursor()
    c.execute("SELECT * FROM user_knowledge WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))
    rows = c.fetchall()
    column_names = [desc[0] for desc in c.description]
    return [dict(zip(column_names, row)) for row in rows]


def update_knowledge_review_content(conn, knowledge_id, review_content):
    ensure_knowledge_schema(conn)
    conn.execute(
        """UPDATE user_knowledge
           SET review_content=?,
               review_generated_at=datetime('now'),
               updated_at=datetime('now')
           WHERE id=?""",
        (review_content or "", knowledge_id),
    )
