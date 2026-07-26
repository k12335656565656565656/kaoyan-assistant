import unittest
from datetime import datetime, timedelta

from services.auth_cookie import (
    AUTH_SESSION_DAYS,
    auth_session_cutoff,
    read_cookie_value,
    select_auth_token,
)


class AuthCookieTests(unittest.TestCase):
    def test_auth_sessions_are_limited_to_seven_days(self):
        now = datetime(2026, 7, 26, 12, 0, 0)

        self.assertEqual(AUTH_SESSION_DAYS, 7)
        self.assertEqual(auth_session_cutoff(now), now - timedelta(days=7))

    def test_read_cookie_value_refreshes_cookie_manager_snapshot(self):
        class FakeCookieManager:
            def __init__(self):
                self.calls = []

            def get_all(self, key):
                self.calls.append(key)
                return {"auth_token": "persisted-token"}

        manager = FakeCookieManager()

        token = read_cookie_value(manager, "auth_token")

        self.assertEqual(token, "persisted-token")
        self.assertEqual(manager.calls, ["auth_cookie_read_auth_token_v1"])

    def test_read_cookie_value_returns_none_for_empty_component_state(self):
        class FakeCookieManager:
            def get_all(self, key):
                return {}

        self.assertIsNone(read_cookie_value(FakeCookieManager(), "auth_token"))

    def test_read_cookie_value_keeps_cached_token_when_refresh_is_temporarily_empty(self):
        class FakeCookieManager:
            def __init__(self):
                self.cookies = {"auth_token": "cached-token"}

            def get_all(self, key):
                self.cookies = {}
                return {}

            def get(self, cookie_name):
                return self.cookies.get(cookie_name)

        self.assertEqual(read_cookie_value(FakeCookieManager(), "auth_token"), "cached-token")

    def test_select_auth_token_keeps_current_session_when_cookie_is_temporarily_empty(self):
        self.assertEqual(
            select_auth_token("", "session-token"),
            "session-token",
        )


if __name__ == "__main__":
    unittest.main()
