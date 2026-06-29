import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from professional_knowledge.catalog import list_enabled_subjects, list_rag_knowledge_bases
from services.local_material_source_service import (
    get_local_material_root,
    get_local_material_source_for_subject,
    list_local_material_files,
    read_local_material,
)


class LocalMaterialSourceServiceTests(unittest.TestCase):
    def test_medical_subject_is_enabled_in_catalog(self):
        subjects = list_enabled_subjects()
        profiles = {item.subject_label: item for item in list_rag_knowledge_bases()}

        self.assertIn("医学考研", subjects)
        self.assertTrue(profiles["医学考研"].enabled)
        self.assertEqual(profiles["医学考研"].stage, "MVP")

    def test_medical_source_can_list_and_read_files_from_env_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes_dir = root / "真题"
            notes_dir.mkdir()
            sample_file = notes_dir / "样例.md"
            sample_file.write_text("医学考研示例资料", encoding="utf-8")

            with patch.dict(os.environ, {"MEDICAL_POSTGRADUATE_ROOT": str(root)}, clear=False):
                profile = get_local_material_source_for_subject("医学考研")
                self.assertIsNotNone(profile)
                self.assertEqual(profile.key, "medical_postgraduate")
                self.assertEqual(get_local_material_root(profile.key), root.resolve())

                files = list_local_material_files(profile.key)
                self.assertEqual(len(files), 1)
                self.assertEqual(files[0]["relative_path"], "真题/样例.md")

                filename, file_bytes = read_local_material(profile.key, "真题/样例.md")
                self.assertEqual(filename, "样例.md")
                self.assertIn("医学考研示例资料", file_bytes.decode("utf-8"))

    def test_read_local_material_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.txt").write_text("safe", encoding="utf-8")
            with patch.dict(os.environ, {"MEDICAL_POSTGRADUATE_ROOT": str(root)}, clear=False):
                with self.assertRaises(RuntimeError):
                    read_local_material("medical_postgraduate", "../outside.txt")


if __name__ == "__main__":
    unittest.main()
