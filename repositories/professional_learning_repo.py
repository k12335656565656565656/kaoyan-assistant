import sqlite3
from datetime import datetime, timedelta


RATING_ORDER = {"again": 0, "hard": 1, "good": 2, "easy": 3}


def ensure_professional_learning_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS professional_memory (
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            knowledge_id INTEGER NOT NULL,
            mastery_score REAL NOT NULL DEFAULT 0.0,
            review_count INTEGER NOT NULL DEFAULT 0,
            correct_count INTEGER NOT NULL DEFAULT 0,
            lapse_count INTEGER NOT NULL DEFAULT 0,
            interval_days INTEGER NOT NULL DEFAULT 0,
            last_reviewed TEXT,
            next_review TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, subject, knowledge_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS professional_study_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            knowledge_id INTEGER,
            study_mode TEXT NOT NULL,
            question TEXT,
            user_answer TEXT,
            feedback TEXT,
            score INTEGER NOT NULL DEFAULT 0,
            rating TEXT NOT NULL DEFAULT 'again',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS ix_professional_study_records_user_subject
           ON professional_study_records(user_id, subject, created_at DESC)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS professional_saved_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            knowledge_id INTEGER,
            question TEXT NOT NULL,
            reference_answer TEXT,
            grading_points_json TEXT,
            source_mode TEXT NOT NULL DEFAULT 'quiz',
            practice_count INTEGER NOT NULL DEFAULT 0,
            last_practiced TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS ix_professional_saved_questions_user_subject
           ON professional_saved_questions(user_id, subject, updated_at DESC)"""
    )


def _initial_mastery(point: dict) -> float:
    state = str(point.get("mastery_state") or "")
    if state == "已掌握":
        return 0.85
    if state == "学习中":
        return 0.55
    return 0.0


def ensure_memory_rows(
    conn: sqlite3.Connection,
    user_id: int,
    subject: str,
    points: list[dict],
) -> None:
    ensure_professional_learning_schema(conn)
    conn.execute(
        """UPDATE professional_memory
           SET mastery_score=0.0
           WHERE user_id=? AND subject=?
             AND review_count=0
             AND correct_count=0
             AND lapse_count=0
             AND ABS(mastery_score - 0.30) < 0.00001""",
        (user_id, subject),
    )
    now = datetime.now().isoformat(timespec="seconds")
    for point in points:
        knowledge_id = point.get("id")
        if knowledge_id is None:
            continue
        conn.execute(
            """INSERT OR IGNORE INTO professional_memory (
                   user_id, subject, knowledge_id, mastery_score, next_review, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, subject, knowledge_id, _initial_mastery(point), now, now),
        )


def list_memory_states(
    conn: sqlite3.Connection,
    user_id: int,
    subject: str,
) -> list[dict]:
    ensure_professional_learning_schema(conn)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT m.*, k.knowledge_name, k.chapter_name, k.review_priority,
                  k.core_definition, k.source_text, k.material_id
           FROM professional_memory m
           LEFT JOIN user_knowledge k ON k.id=m.knowledge_id
           WHERE m.user_id=? AND m.subject=?
           ORDER BY m.mastery_score ASC,
                    CASE WHEN m.next_review IS NULL THEN 0 ELSE 1 END,
                    m.next_review ASC,
                    m.knowledge_id DESC""",
        (user_id, subject),
    ).fetchall()
    return [dict(row) for row in rows]


def _next_schedule(
    old_mastery: float,
    old_interval: int,
    review_count: int,
    score: int,
    rating: str,
) -> tuple[float, int]:
    normalized = max(0.0, min(1.0, score / 100.0))
    if rating == "again":
        return max(0.05, min(old_mastery * 0.65, normalized * 0.70)), 1
    if rating == "hard":
        mastery = max(old_mastery * 0.92, normalized * 0.78)
        return min(0.85, mastery), max(1, round(max(1, old_interval) * 1.25))
    if rating == "easy":
        mastery = max(old_mastery + 0.18, normalized * 0.92)
        interval = 5 if review_count == 0 else max(5, round(max(1, old_interval) * 3.0))
        return min(1.0, mastery), interval
    mastery = max(old_mastery + 0.10, normalized * 0.86)
    interval = 3 if review_count == 0 else max(2, round(max(1, old_interval) * 2.1))
    return min(0.96, mastery), interval


def record_study_result(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    subject: str,
    knowledge_id: int | None,
    study_mode: str,
    question: str,
    user_answer: str,
    feedback: str,
    score: int,
    rating: str,
) -> dict:
    ensure_professional_learning_schema(conn)
    rating = rating if rating in RATING_ORDER else "again"
    score = max(0, min(100, int(score or 0)))
    now_dt = datetime.now()
    now = now_dt.isoformat(timespec="seconds")

    conn.execute(
        """INSERT INTO professional_study_records (
               user_id, subject, knowledge_id, study_mode, question,
               user_answer, feedback, score, rating, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            subject,
            knowledge_id,
            study_mode,
            question,
            user_answer,
            feedback,
            score,
            rating,
            now,
        ),
    )

    if knowledge_id is None:
        return {"mastery_score": score / 100.0, "next_review": None, "interval_days": 0}

    row = conn.execute(
        """SELECT mastery_score, review_count, correct_count, lapse_count, interval_days
           FROM professional_memory
           WHERE user_id=? AND subject=? AND knowledge_id=?""",
        (user_id, subject, knowledge_id),
    ).fetchone()
    if row is None:
        conn.execute(
            """INSERT INTO professional_memory (
                   user_id, subject, knowledge_id, mastery_score, next_review, updated_at
               ) VALUES (?, ?, ?, 0.0, ?, ?)""",
            (user_id, subject, knowledge_id, now, now),
        )
        old_mastery, review_count, correct_count, lapse_count, old_interval = 0.0, 0, 0, 0, 0
    else:
        old_mastery, review_count, correct_count, lapse_count, old_interval = row

    mastery, interval_days = _next_schedule(
        float(old_mastery or 0.0),
        int(old_interval or 0),
        int(review_count or 0),
        score,
        rating,
    )
    next_review = (now_dt + timedelta(days=interval_days)).isoformat(timespec="seconds")
    conn.execute(
        """UPDATE professional_memory
           SET mastery_score=?, review_count=?, correct_count=?, lapse_count=?,
               interval_days=?, last_reviewed=?, next_review=?, updated_at=?
           WHERE user_id=? AND subject=? AND knowledge_id=?""",
        (
            mastery,
            int(review_count or 0) + 1,
            int(correct_count or 0) + (1 if score >= 70 else 0),
            int(lapse_count or 0) + (1 if score < 60 else 0),
            interval_days,
            now,
            next_review,
            now,
            user_id,
            subject,
            knowledge_id,
        ),
    )
    mastery_state = "已掌握" if mastery >= 0.80 else "学习中" if mastery >= 0.45 else "待复习"
    conn.execute(
        "UPDATE user_knowledge SET mastery_state=?, updated_at=? WHERE id=? AND user_id=?",
        (mastery_state, now, knowledge_id, user_id),
    )
    return {
        "mastery_score": mastery,
        "next_review": next_review,
        "interval_days": interval_days,
    }


def set_review_due_now(
    conn: sqlite3.Connection,
    user_id: int,
    subject: str,
    knowledge_id: int,
) -> None:
    ensure_professional_learning_schema(conn)
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """UPDATE professional_memory
           SET next_review=?, updated_at=?
           WHERE user_id=? AND subject=? AND knowledge_id=?""",
        (now, now, user_id, subject, knowledge_id),
    )


def save_generated_question(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    subject: str,
    knowledge_id: int | None,
    question: str,
    reference_answer: str,
    grading_points: list[str],
    source_mode: str,
) -> dict:
    ensure_professional_learning_schema(conn)
    import json

    now = datetime.now().isoformat(timespec="seconds")
    cursor = conn.execute(
        """INSERT INTO professional_saved_questions (
               user_id, subject, knowledge_id, question, reference_answer,
               grading_points_json, source_mode, created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            subject,
            knowledge_id,
            question,
            reference_answer,
            json.dumps(grading_points or [], ensure_ascii=False),
            source_mode,
            now,
            now,
        ),
    )
    saved_id = cursor.lastrowid
    return {"id": saved_id, "question": question}


def list_saved_questions(
    conn: sqlite3.Connection,
    user_id: int,
    subject: str,
    *,
    limit: int = 30,
) -> list[dict]:
    ensure_professional_learning_schema(conn)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT q.*, k.knowledge_name, k.chapter_name
           FROM professional_saved_questions q
           LEFT JOIN user_knowledge k ON k.id=q.knowledge_id
           WHERE q.user_id=? AND q.subject=?
           ORDER BY q.practice_count ASC,
                    CASE WHEN q.last_practiced IS NULL THEN 0 ELSE 1 END,
                    q.last_practiced ASC,
                    q.updated_at DESC
           LIMIT ?""",
        (user_id, subject, max(1, int(limit))),
    ).fetchall()
    return [dict(row) for row in rows]


def mark_saved_question_practiced(
    conn: sqlite3.Connection,
    saved_question_id: int,
) -> None:
    ensure_professional_learning_schema(conn)
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """UPDATE professional_saved_questions
           SET practice_count=practice_count+1,
               last_practiced=?,
               updated_at=?
           WHERE id=?""",
        (now, now, saved_question_id),
    )


def list_recent_study_records(
    conn: sqlite3.Connection,
    user_id: int,
    subject: str,
    *,
    study_mode: str | None = None,
    limit: int = 20,
) -> list[dict]:
    ensure_professional_learning_schema(conn)
    conn.row_factory = sqlite3.Row
    query = """SELECT r.*, k.knowledge_name, k.chapter_name
               FROM professional_study_records r
               LEFT JOIN user_knowledge k ON k.id=r.knowledge_id
               WHERE r.user_id=? AND r.subject=?"""
    params: list[object] = [user_id, subject]
    if study_mode:
        query += " AND r.study_mode=?"
        params.append(study_mode)
    query += " ORDER BY r.id DESC LIMIT ?"
    params.append(max(1, int(limit)))
    rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]
