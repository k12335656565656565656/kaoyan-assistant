from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime


MEMORY_DB = os.environ.get("MEMORY_DB", "data/memory.db")


STRUCTURED_COLUMNS = {
    "source_text": "TEXT",
    "source_filename": "TEXT",
    "source_file_type": "TEXT",
    "tags_json": "TEXT",
    "updated_at": "TEXT",
}


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(MEMORY_DB) or "data", exist_ok=True)
    return sqlite3.connect(MEMORY_DB)


def ensure_wrong_question_schema(conn: sqlite3.Connection) -> None:
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS user_wrong_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            knowledge_id INTEGER,
            subject TEXT,
            chapter_name TEXT,
            question TEXT,
            user_answer TEXT,
            correct_answer TEXT,
            explanation TEXT,
            error_count INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',
            last_reviewed TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )

    existing_columns = {row[1] for row in c.execute("PRAGMA table_info(user_wrong_questions)").fetchall()}
    for column_name, column_type in STRUCTURED_COLUMNS.items():
        if column_name not in existing_columns:
            c.execute(f"ALTER TABLE user_wrong_questions ADD COLUMN {column_name} {column_type}")


def _parse_tags(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except Exception:
        pass
    return [item.strip() for item in str(value).split(",") if item.strip()]


def count_user_wrong_questions(user_id: int, *, status: str | None = None) -> int:
    conn = _connect()
    try:
        ensure_wrong_question_schema(conn)
        query = "SELECT COUNT(*) FROM user_wrong_questions WHERE user_id=?"
        params: list = [user_id]
        if status:
            query += " AND status=?"
            params.append(status)
        return conn.execute(query, tuple(params)).fetchone()[0] or 0
    finally:
        conn.close()


def bulk_create_wrong_questions(user_id: int, items: list[dict]) -> int:
    if not items:
        return 0

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect()
    try:
        ensure_wrong_question_schema(conn)
        c = conn.cursor()
        saved_count = 0
        for item in items:
            tags_json = json.dumps(_parse_tags(item.get("tags")), ensure_ascii=False)
            c.execute(
                """INSERT INTO user_wrong_questions (
                    user_id, knowledge_id, subject, chapter_name, question, user_answer,
                    correct_answer, explanation, error_count, status, last_reviewed,
                    created_at, source_text, source_filename, source_file_type, tags_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    item.get("knowledge_id"),
                    item.get("subject", ""),
                    item.get("chapter_name", ""),
                    item.get("question", ""),
                    item.get("user_answer", ""),
                    item.get("correct_answer", ""),
                    item.get("explanation", ""),
                    int(item.get("error_count") or 1),
                    item.get("status", "active"),
                    item.get("last_reviewed"),
                    now_str,
                    item.get("source_text", ""),
                    item.get("source_filename", ""),
                    item.get("source_file_type", ""),
                    tags_json,
                    now_str,
                ),
            )
            saved_count += 1
        conn.commit()
        return saved_count
    finally:
        conn.close()


def list_user_wrong_questions(
    user_id: int,
    *,
    subject: str | None = None,
    status: str | None = None,
    search: str = "",
    limit: int = 200,
) -> list[dict]:
    conn = _connect()
    try:
        ensure_wrong_question_schema(conn)
        conn.row_factory = None
        query = "SELECT * FROM user_wrong_questions WHERE user_id=?"
        params: list = [user_id]
        if subject and subject != "全部":
            query += " AND subject=?"
            params.append(subject)
        if status and status != "全部":
            query += " AND status=?"
            params.append(status)

        search = (search or "").strip()
        if search:
            query += """ AND (
                question LIKE ?
                OR correct_answer LIKE ?
                OR explanation LIKE ?
                OR chapter_name LIKE ?
                OR source_filename LIKE ?
            )"""
            fuzzy = f"%{search}%"
            params.extend([fuzzy, fuzzy, fuzzy, fuzzy, fuzzy])

        query += " ORDER BY CASE WHEN status='active' THEN 0 ELSE 1 END, COALESCE(last_reviewed, created_at) ASC, id DESC LIMIT ?"
        params.append(limit)
        c = conn.cursor()
        c.execute(query, tuple(params))
        rows = c.fetchall()
        column_names = [desc[0] for desc in c.description]
        result = []
        for row in rows:
            payload = dict(zip(column_names, row))
            payload["tags"] = _parse_tags(payload.get("tags_json"))
            result.append(payload)
        return result
    finally:
        conn.close()


def update_wrong_question_status(question_id: int, status: str) -> None:
    conn = _connect()
    try:
        ensure_wrong_question_schema(conn)
        conn.execute(
            """UPDATE user_wrong_questions
               SET status=?, updated_at=datetime('now')
               WHERE id=?""",
            (status, question_id),
        )
        conn.commit()
    finally:
        conn.close()


def touch_wrong_question_review(question_id: int) -> None:
    conn = _connect()
    try:
        ensure_wrong_question_schema(conn)
        conn.execute(
            """UPDATE user_wrong_questions
               SET status='active',
                   last_reviewed=datetime('now'),
                   updated_at=datetime('now')
               WHERE id=?""",
            (question_id,),
        )
        conn.commit()
    finally:
        conn.close()


def delete_wrong_question(question_id: int) -> None:
    conn = _connect()
    try:
        ensure_wrong_question_schema(conn)
        conn.execute("DELETE FROM user_wrong_questions WHERE id=?", (question_id,))
        conn.commit()
    finally:
        conn.close()
