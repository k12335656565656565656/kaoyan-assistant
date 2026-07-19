"""Shared, database-backed authentication helpers for Streamlit entrypoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import sqlite3
from collections.abc import MutableMapping


class AuthenticationRequired(RuntimeError):
    """Raised when a data operation is attempted without an authenticated user."""


def _password_hash(password: str) -> str:
    """Keep compatibility with the project's existing user password hashes."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_auth_schema(conn: sqlite3.Connection) -> None:
    """Create the shared user/session schema without changing existing user data."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            display_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    for column, definition in (
        ("password_hash", "TEXT"),
        ("display_name", "TEXT"),
        ("login_token", "TEXT"),
    ):
        try:
            conn.execute(f"SELECT {column} FROM users LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")

    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_digest TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_sessions_active "
        "ON user_sessions(token_digest, expires_at, revoked_at)"
    )


def register_user(database_path: str, username: str, password: str) -> int | None:
    username = (username or "").strip()
    if not username or not password:
        return None
    conn = sqlite3.connect(database_path)
    try:
        ensure_auth_schema(conn)
        try:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)",
                (username, _password_hash(password), username),
            )
        except sqlite3.IntegrityError:
            return None
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def authenticate_user(database_path: str, username: str, password: str) -> dict | None:
    conn = sqlite3.connect(database_path)
    try:
        ensure_auth_schema(conn)
        row = conn.execute(
            "SELECT id, username FROM users WHERE username=? AND password_hash=?",
            ((username or "").strip(), _password_hash(password or "")),
        ).fetchone()
    finally:
        conn.close()
    return {"user_id": int(row[0]), "username": row[1]} if row else None


def create_login_session(database_path: str, user_id: int, *, days: int = 30) -> str:
    token = secrets.token_urlsafe(48)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    conn = sqlite3.connect(database_path)
    try:
        ensure_auth_schema(conn)
        conn.execute(
            "INSERT INTO user_sessions (user_id, token_digest, expires_at) VALUES (?, ?, ?)",
            (int(user_id), _token_digest(token), expires_at),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def verify_login_session(database_path: str, token: str | None) -> dict | None:
    if not token:
        return None
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(database_path)
    try:
        ensure_auth_schema(conn)
        row = conn.execute(
            """SELECT users.id, users.username
               FROM user_sessions
               JOIN users ON users.id=user_sessions.user_id
               WHERE user_sessions.token_digest=?
                 AND user_sessions.revoked_at IS NULL
                 AND user_sessions.expires_at>?""",
            (_token_digest(token), now),
        ).fetchone()
    finally:
        conn.close()
    return {"user_id": int(row[0]), "username": row[1]} if row else None


def revoke_login_session(database_path: str, token: str | None) -> None:
    if not token:
        return
    conn = sqlite3.connect(database_path)
    try:
        ensure_auth_schema(conn)
        conn.execute(
            "UPDATE user_sessions SET revoked_at=? WHERE token_digest=? AND revoked_at IS NULL",
            (datetime.now(timezone.utc).isoformat(), _token_digest(token)),
        )
        conn.commit()
    finally:
        conn.close()


def clear_user_session_state(
    state: MutableMapping,
    *,
    preserve_keys: set[str] | None = None,
) -> None:
    """Remove every identity-bound Streamlit value before an account changes."""
    preserved = preserve_keys or set()
    for key in list(state.keys()):
        if key not in preserved:
            del state[key]


def activate_authenticated_user(
    state: MutableMapping,
    user_info: dict,
    token: str,
    *,
    preserve_keys: set[str] | None = None,
) -> None:
    """Reset stale UI state, then install one explicit authenticated identity."""
    clear_user_session_state(state, preserve_keys=preserve_keys)
    state["logged_in"] = True
    state["user_id"] = int(user_info["user_id"])
    state["username"] = str(user_info["username"])
    state["auth_token"] = token
    state["page"] = "hub"


def require_user_id(state: MutableMapping) -> int:
    user_id = state.get("user_id")
    if not state.get("logged_in") or not isinstance(user_id, int) or user_id <= 0:
        raise AuthenticationRequired("未登录，不能访问用户数据")
    return user_id
