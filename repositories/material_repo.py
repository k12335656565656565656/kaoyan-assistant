from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any


MATERIAL_COLUMNS = {
    "user_id": "INTEGER",
    "subject": "TEXT",
    "filename": "TEXT",
    "chapter_name": "TEXT",
    "file_path": "TEXT",
    "file_type": "TEXT",
    "processing_status": "TEXT DEFAULT 'pending'",
    "knowledge_count": "INTEGER DEFAULT 0",
    "created_at": "TEXT",
    "subject_key": "TEXT",
    "source_type": "TEXT",
    "process_method": "TEXT",
    "raw_extracted_text": "TEXT",
    "extracted_text": "TEXT",
    "confirmed_text": "TEXT",
    "material_result_json": "TEXT",
    "workflow_snapshot_json": "TEXT",
    "content_hash": "TEXT",
    "error_message": "TEXT",
    "updated_at": "TEXT",
}


def ensure_material_schema(conn) -> None:
    """Create the material table or add missing columns without replacing old rows."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT,
            filename TEXT,
            chapter_name TEXT,
            file_path TEXT,
            file_type TEXT,
            processing_status TEXT DEFAULT 'pending',
            knowledge_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            subject_key TEXT,
            source_type TEXT,
            process_method TEXT,
            raw_extracted_text TEXT,
            extracted_text TEXT,
            confirmed_text TEXT,
            material_result_json TEXT,
            workflow_snapshot_json TEXT,
            content_hash TEXT,
            error_message TEXT,
            updated_at TEXT
        )"""
    )
    existing_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(user_materials)").fetchall()
    }
    for column_name, column_type in MATERIAL_COLUMNS.items():
        if column_name not in existing_columns:
            conn.execute(
                f"ALTER TABLE user_materials ADD COLUMN {column_name} {column_type}"
            )

    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_user_materials_resumable
           ON user_materials(user_id, processing_status, updated_at)"""
    )


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _as_payload(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
            return payload if isinstance(payload, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    if is_dataclass(value):
        try:
            payload = asdict(value)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            payload = to_dict()
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}
    return {}


def _dump_json(value: Any) -> str:
    try:
        return json.dumps(value if value is not None else {}, ensure_ascii=False)
    except (TypeError, ValueError):
        return "{}"


def _load_json(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _content_hash(text: Any) -> str:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _row_to_dict(cursor, row) -> dict:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        payload = {key: row[key] for key in row.keys()}
    else:
        column_names = [description[0] for description in cursor.description]
        payload = dict(zip(column_names, row))
    payload["material_result"] = _load_json(payload.get("material_result_json"))
    payload["workflow_snapshot"] = _load_json(
        payload.get("workflow_snapshot_json")
    )
    return payload


def create_material(
    conn,
    user_id: int,
    subject: str = "",
    filename: str = "",
    chapter_name: str = "",
    file_path: str = "",
    file_type: str = "",
    *,
    subject_key: str = "",
    source_type: str = "",
    process_method: str = "",
    raw_extracted_text: str = "",
    extracted_text: str = "",
    confirmed_text: str = "",
    material_result: Any = None,
    workflow_snapshot: Any = None,
    content_hash: str = "",
    processing_status: str = "pending",
    status: str | None = None,
    error_message: str = "",
) -> dict:
    ensure_material_schema(conn)
    now_str = _now()
    result_payload = _as_payload(material_result)
    snapshot_payload = _as_payload(workflow_snapshot)
    extracted_text = extracted_text or result_payload.get("extracted_text", "")
    raw_extracted_text = raw_extracted_text or result_payload.get(
        "raw_extracted_text", ""
    )
    source_type = source_type or result_payload.get("source_type", "")
    process_method = process_method or result_payload.get("process_method", "")
    content_hash = content_hash or _content_hash(
        confirmed_text or extracted_text or raw_extracted_text
    )
    cursor = conn.execute(
        """INSERT INTO user_materials (
            user_id, subject, subject_key, filename, chapter_name, file_path,
            file_type, source_type, process_method, processing_status,
            knowledge_count, raw_extracted_text, extracted_text, confirmed_text,
            material_result_json, workflow_snapshot_json, content_hash,
            error_message, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            subject or "",
            subject_key or "",
            filename or "",
            chapter_name or "",
            file_path or "",
            file_type or "",
            source_type or "",
            process_method or "",
            status or processing_status or "pending",
            0,
            raw_extracted_text or "",
            extracted_text or "",
            confirmed_text or "",
            _dump_json(result_payload),
            _dump_json(snapshot_payload),
            content_hash or "",
            error_message or "",
            now_str,
            now_str,
        ),
    )
    return get_material(conn, cursor.lastrowid)


def save_extraction_result(
    conn,
    material_id: int,
    material_result: Any = None,
    **updates,
) -> dict:
    ensure_material_schema(conn)
    if material_result is None:
        material_result = updates.pop("result", None)
    result_payload = _as_payload(material_result)

    raw_text = updates.pop(
        "raw_extracted_text", result_payload.get("raw_extracted_text", "")
    )
    extracted_text = updates.pop(
        "extracted_text", result_payload.get("extracted_text", "")
    )
    source_type = updates.pop("source_type", result_payload.get("source_type", ""))
    process_method = updates.pop(
        "process_method", result_payload.get("process_method", "")
    )
    status = updates.pop(
        "status", updates.pop("processing_status", "extracted")
    )
    content_hash = updates.pop("content_hash", "") or _content_hash(
        extracted_text or raw_text
    )
    error_message = updates.pop("error_message", "")

    conn.execute(
        """UPDATE user_materials
           SET source_type=?, process_method=?, raw_extracted_text=?,
               extracted_text=?, material_result_json=?, content_hash=?,
               processing_status=?, error_message=?, updated_at=?
           WHERE id=?""",
        (
            source_type or "",
            process_method or "",
            raw_text or "",
            extracted_text or "",
            _dump_json(result_payload),
            content_hash or "",
            status or "extracted",
            error_message or "",
            _now(),
            material_id,
        ),
    )
    return get_material(conn, material_id)


def save_confirmed_text(
    conn,
    material_id: int,
    confirmed_text: str,
    *,
    content_hash: str = "",
    status: str = "text_confirmed",
) -> dict:
    ensure_material_schema(conn)
    conn.execute(
        """UPDATE user_materials
           SET confirmed_text=?, content_hash=?, processing_status=?,
               error_message='', updated_at=?
           WHERE id=?""",
        (
            confirmed_text or "",
            content_hash or _content_hash(confirmed_text),
            status or "text_confirmed",
            _now(),
            material_id,
        ),
    )
    return get_material(conn, material_id)


def save_workflow_snapshot(
    conn,
    material_id: int,
    workflow_snapshot: Any,
    *,
    status: str | None = None,
) -> dict:
    ensure_material_schema(conn)
    assignments = ["workflow_snapshot_json=?", "updated_at=?"]
    params: list[Any] = [
        _dump_json(_as_payload(workflow_snapshot)),
        _now(),
    ]
    if status:
        assignments.append("processing_status=?")
        params.append(status)
    params.append(material_id)
    conn.execute(
        f"UPDATE user_materials SET {', '.join(assignments)} WHERE id=?",
        tuple(params),
    )
    return get_material(conn, material_id)


def mark_material_status(
    conn,
    material_id: int,
    status: str,
    error_message: str | None = None,
) -> dict:
    ensure_material_schema(conn)
    if error_message is None:
        conn.execute(
            """UPDATE user_materials
               SET processing_status=?, updated_at=? WHERE id=?""",
            (status, _now(), material_id),
        )
    else:
        conn.execute(
            """UPDATE user_materials
               SET processing_status=?, error_message=?, updated_at=? WHERE id=?""",
            (status, error_message or "", _now(), material_id),
        )
    return get_material(conn, material_id)


def get_material(conn, material_id: int) -> dict:
    ensure_material_schema(conn)
    cursor = conn.execute("SELECT * FROM user_materials WHERE id=?", (material_id,))
    return _row_to_dict(cursor, cursor.fetchone())


def list_resumable_materials(
    conn,
    user_id: int,
    subject_key: str | None = None,
    limit: int = 20,
) -> list[dict]:
    ensure_material_schema(conn)
    query = """SELECT * FROM user_materials
               WHERE user_id=?
                 AND COALESCE(processing_status, 'pending') NOT IN ('done', 'completed')"""
    params: list[Any] = [user_id]
    if subject_key:
        query += " AND subject_key=?"
        params.append(subject_key)
    query += " ORDER BY COALESCE(updated_at, created_at) DESC, id DESC LIMIT ?"
    params.append(max(1, int(limit)))
    cursor = conn.execute(query, tuple(params))
    return [_row_to_dict(cursor, row) for row in cursor.fetchall()]
