import os
import tempfile
import unittest

from services.auth_service import (
    AuthenticationRequired,
    activate_authenticated_user,
    authenticate_user,
    create_login_session,
    register_user,
    require_user_id,
    revoke_login_session,
    verify_login_session,
)


class AuthServiceTests(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_sessions_are_bound_to_their_own_users(self):
        alice_id = register_user(self.db_path, "alice", "secret")
        bob_id = register_user(self.db_path, "bob", "secret")
        alice_token = create_login_session(self.db_path, alice_id)
        bob_token = create_login_session(self.db_path, bob_id)

        self.assertEqual(verify_login_session(self.db_path, alice_token)["user_id"], alice_id)
        self.assertEqual(verify_login_session(self.db_path, bob_token)["user_id"], bob_id)
        self.assertEqual(authenticate_user(self.db_path, "alice", "secret")["user_id"], alice_id)

        revoke_login_session(self.db_path, alice_token)
        self.assertIsNone(verify_login_session(self.db_path, alice_token))
        self.assertEqual(verify_login_session(self.db_path, bob_token)["user_id"], bob_id)

    def test_account_switch_discards_stale_business_state(self):
        state = {
            "cookie_manager": object(),
            "logged_in": True,
            "user_id": 1,
            "username": "alice",
            "_last_answer_text": "Alice private answer",
            "knowledge_drafts": [{"question": "Alice draft"}],
            "wrong_question_drafts": [{"question": "Alice wrong question"}],
        }

        activate_authenticated_user(
            state,
            {"user_id": 2, "username": "bob"},
            "bob-token",
            preserve_keys={"cookie_manager"},
        )

        self.assertEqual(state["user_id"], 2)
        self.assertEqual(state["username"], "bob")
        self.assertNotIn("_last_answer_text", state)
        self.assertNotIn("knowledge_drafts", state)
        self.assertNotIn("wrong_question_drafts", state)
        self.assertIn("cookie_manager", state)

    def test_unauthenticated_state_has_no_default_user(self):
        with self.assertRaises(AuthenticationRequired):
            require_user_id({"logged_in": False})


if __name__ == "__main__":
    unittest.main()
