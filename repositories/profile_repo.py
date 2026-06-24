from __future__ import annotations

from repositories.sqlite_utils import connect


def list_profile_columns(db_path: str) -> list[str]:
    with connect(db_path) as conn:
        rows = conn.execute("PRAGMA table_info(user_profiles)").fetchall()
    return [row[1] for row in rows]


def get_user_profile(db_path: str, user_id: int) -> dict:
    columns = list_profile_columns(db_path)
    if not columns:
        return {}
    with connect(db_path, row_factory=None) as conn:
        row = conn.execute("SELECT * FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return {}
    return dict(zip(columns, row))


def save_profile_field(db_path: str, user_id: int, field: str, value) -> None:
    allowed = set(list_profile_columns(db_path)) - {"id", "user_id", "created_at", "updated_at"}
    if field not in allowed:
        raise ValueError(f"非法字段: {field}")

    with connect(db_path, row_factory=None) as conn:
        exists = conn.execute("SELECT 1 FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
        if exists:
            conn.execute(
                f"UPDATE user_profiles SET {field}=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                (value, user_id),
            )
        else:
            conn.execute(
                f"INSERT INTO user_profiles (user_id, {field}) VALUES (?, ?)",
                (user_id, value),
            )
        conn.commit()


def save_profile_fields(db_path: str, user_id: int, fields: dict) -> None:
    for field, value in fields.items():
        save_profile_field(db_path, user_id, field, value)
