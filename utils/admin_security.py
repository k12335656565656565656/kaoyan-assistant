"""Small, testable helpers for the admin password lifecycle."""

import hmac
import os
from pathlib import Path
import secrets


INSECURE_LEGACY_PASSWORD = "777888AA"


def load_admin_password(password_file: Path, env_password=None):
    configured = (env_password if env_password is not None else os.getenv("ADMIN_PASSWORD", "")).strip()
    if configured:
        return configured

    password_file = Path(password_file).expanduser()
    if password_file.exists():
        stored = password_file.read_text(encoding="utf-8").strip()
        if stored and stored != INSECURE_LEGACY_PASSWORD:
            return stored

    generated = secrets.token_urlsafe(24)
    password_file.parent.mkdir(parents=True, exist_ok=True)
    password_file.write_text(generated, encoding="utf-8")
    try:
        os.chmod(password_file, 0o600)
    except OSError:
        pass
    return generated


def password_matches(candidate, expected):
    return hmac.compare_digest(str(candidate or ""), str(expected or ""))
