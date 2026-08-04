import sqlite3
import tempfile
import unittest
from pathlib import Path

from migrate_db import migrate
from utils.admin_security import INSECURE_LEGACY_PASSWORD, load_admin_password, password_matches


class AdminCompatibilityTests(unittest.TestCase):
    def test_admin_password_uses_environment_and_constant_time_match(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "admin.pass"
            self.assertEqual(load_admin_password(path, "from-env"), "from-env")
            self.assertFalse(path.exists())
            self.assertTrue(password_matches("from-env", "from-env"))
            self.assertFalse(password_matches("wrong", "from-env"))

    def test_public_legacy_password_is_replaced_with_random_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "admin.pass"
            path.write_text(INSECURE_LEGACY_PASSWORD, encoding="utf-8")

            password = load_admin_password(path, "")

            self.assertTrue(password)
            self.assertNotEqual(password, INSECURE_LEGACY_PASSWORD)
            self.assertEqual(path.read_text(encoding="utf-8"), password)

    def test_migration_is_explicit_and_creates_a_backup_before_schema_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.db"
            connection = sqlite3.connect(db_path)
            connection.execute("CREATE TABLE visit_log (id INTEGER PRIMARY KEY)")
            connection.commit()
            connection.close()

            result = migrate(db_path)

            self.assertTrue(Path(result["backup"]).exists())
            connection = sqlite3.connect(db_path)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            connection.close()
            self.assertTrue({"question_analysis", "rag_record", "user_feedback", "classification_cache"} <= tables)


if __name__ == "__main__":
    unittest.main()
