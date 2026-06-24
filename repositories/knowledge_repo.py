import json
from datetime import datetime

from schemas.knowledge_schema import knowledge_point_to_dict


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


def save_confirmed_knowledge_points(conn, user_id, points, material_meta=None) -> int:
    ensure_knowledge_schema(conn)
    material_meta = material_meta or {}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c = conn.cursor()
    saved_count = 0

    for point in points or []:
        point_dict = knowledge_point_to_dict(point)
        content = _build_legacy_content(point_dict)
        raw_json = json.dumps(point_dict, ensure_ascii=False)

        c.execute(
            """INSERT INTO user_knowledge (
                user_id, material_id, subject, chapter_name, knowledge_name, content,
                knowledge_type, core_definition, exam_question_styles_json, keywords_json,
                related_concepts_json, pitfalls_json, example_or_application, review_priority,
                source_text, source_page, source_location, tags_json, mastery_state,
                is_ai_expansion, uncertainty_note, raw_json, source_type, process_method,
                material_filename, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                material_meta.get("material_id"),
                point_dict.get("subject") or material_meta.get("subject", ""),
                point_dict.get("chapter_name") or material_meta.get("chapter_name", ""),
                point_dict.get("knowledge_name", ""),
                content,
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
        saved_count += 1

    material_id = material_meta.get("material_id")
    if saved_count and material_id and _table_exists(conn, "user_materials"):
        c.execute(
            """UPDATE user_materials
               SET processing_status='done',
                   knowledge_count=COALESCE(knowledge_count, 0) + ?
               WHERE id=?""",
            (saved_count, material_id),
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
