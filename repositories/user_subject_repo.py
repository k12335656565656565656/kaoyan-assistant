"""Per-user custom professional-course profiles."""

from __future__ import annotations

import json
from datetime import datetime

from professional_knowledge.builtin_registry import canonical_fixed_subject


def ensure_user_subject_schema(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_subject_profiles (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               user_id INTEGER NOT NULL,
               subject_key TEXT NOT NULL,
               subject_label TEXT NOT NULL,
               profile_json TEXT NOT NULL,
               enabled INTEGER NOT NULL DEFAULT 1,
               created_at TEXT NOT NULL,
               updated_at TEXT NOT NULL,
               UNIQUE(user_id, subject_key)
           )"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS ix_user_subject_profiles_user_enabled
           ON user_subject_profiles(user_id, enabled)"""
    )


def list_user_subject_profiles(conn, user_id, *, include_disabled=False):
    ensure_user_subject_schema(conn)
    sql = (
        "SELECT subject_key, subject_label, profile_json, enabled "
        "FROM user_subject_profiles WHERE user_id=?"
    )
    params = [int(user_id)]
    if not include_disabled:
        sql += " AND enabled=1"
    sql += " ORDER BY id"
    rows = conn.execute(sql, params).fetchall()
    profiles = []
    for subject_key, subject_label, profile_json, enabled in rows:
        try:
            profile = json.loads(profile_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(profile, dict):
            continue
        profile["key"] = subject_key
        profile.setdefault("catalog", {})["subject_label"] = subject_label
        profile["catalog"]["enabled"] = bool(enabled)
        profiles.append(profile)
    return profiles


def save_user_subject_profile(conn, user_id, profile):
    ensure_user_subject_schema(conn)
    key = str(profile.get("key") or "").strip()
    catalog = profile.get("catalog") if isinstance(profile.get("catalog"), dict) else {}
    label = str(catalog.get("subject_label") or "").strip()
    if not key or not label:
        raise ValueError("自建专业课缺少 key 或名称。")
    if canonical_fixed_subject(label):
        raise ValueError("该名称属于系统固定专业课，请直接使用内置课程。")
    now = datetime.now().isoformat(timespec="seconds")
    payload = json.dumps(profile, ensure_ascii=False, sort_keys=True)
    conn.execute(
        """INSERT INTO user_subject_profiles
               (user_id, subject_key, subject_label, profile_json, enabled, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id, subject_key) DO UPDATE SET
               subject_label=excluded.subject_label,
               profile_json=excluded.profile_json,
               enabled=excluded.enabled,
               updated_at=excluded.updated_at""",
        (
            int(user_id),
            key,
            label,
            payload,
            1 if catalog.get("enabled", True) else 0,
            now,
            now,
        ),
    )
    return profile


def set_user_subject_enabled(conn, user_id, subject_key, enabled):
    ensure_user_subject_schema(conn)
    cursor = conn.execute(
        """UPDATE user_subject_profiles
           SET enabled=?, updated_at=?
           WHERE user_id=? AND subject_key=?""",
        (
            1 if enabled else 0,
            datetime.now().isoformat(timespec="seconds"),
            int(user_id),
            str(subject_key or "").strip(),
        ),
    )
    if cursor.rowcount < 1:
        raise ValueError("未找到这门自建专业课。")
