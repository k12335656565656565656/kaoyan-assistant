from __future__ import annotations

from datetime import timedelta


AUTH_SESSION_DAYS = 7


def auth_session_cutoff(now):
    """Return the oldest creation time accepted for an auth session."""
    return now - timedelta(days=AUTH_SESSION_DAYS)


def read_cookie_value(cookie_manager, cookie_name):
    """Refresh the browser cookie snapshot before reading one cookie value."""
    try:
        cached_value = cookie_manager.get(cookie_name)
    except Exception:
        cached_value = None

    cookies = cookie_manager.get_all(key=f"auth_cookie_read_{cookie_name}_v1")
    if isinstance(cookies, dict) and cookies.get(cookie_name):
        return cookies.get(cookie_name)
    # CookieManager.set() updates its in-memory snapshot before the browser
    # component has necessarily returned the refreshed cookie list.
    return cached_value


def select_auth_token(cookie_token, session_token):
    """Prefer the browser cookie while tolerating one empty component snapshot."""
    cookie_token = str(cookie_token or "").strip()
    if cookie_token:
        return cookie_token
    return str(session_token or "").strip()
