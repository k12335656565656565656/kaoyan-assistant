import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from professional_knowledge.catalog import (
    get_rag_knowledge_base_by_subject,
    list_enabled_subjects,
    list_rag_knowledge_bases,
    save_custom_subject_profile,
)
import professional_knowledge.catalog as catalog_module
from services.local_material_source_service import (
    get_local_material_root,
    get_local_material_source_for_subject,
    list_local_material_files,
    read_local_material,
)


class LocalMaterialSourceServiceTests(unittest.TestCase):
    def setUp(self):
        self._catalog_temp_dir = tempfile.TemporaryDirectory()
        isolated_config = Path(self._catalog_temp_dir.name) / "custom_subjects.json"
        self._catalog_config_patch = patch.object(
            catalog_module,
            "CUSTOM_SUBJECTS_CONFIG_PATH",
            isolated_config,
        )
        self._catalog_config_patch.start()

    def tearDown(self):
        self._catalog_config_patch.stop()
        self._catalog_temp_dir.cleanup()

    def test_default_profiles_keep_existing_subject_behavior_and_extraction_settings(self):
        profiles = {item.key: item for item in list_rag_knowledge_bases()}

        self.assertEqual(
            list(profiles),
            ["exam_408", "exam_history_313"],
        )
        self.assertEqual(profiles["exam_408"].max_points, 100)
        self.assertTrue(profiles["exam_408"].extraction_guidance)
        self.assertTrue(profiles["exam_history_313"].enabled)
        self.assertEqual(
            get_local_material_source_for_subject("408综合").key,
            "exam_408",
        )
        self.assertIsNone(get_local_material_source_for_subject("教育学"))

    def test_legacy_medical_source_remains_available_to_local_material_api(self):
        self.assertNotIn("医学考研", list_enabled_subjects())
        profile = get_local_material_source_for_subject("医学考研")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.key, "medical_postgraduate")

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

    def test_custom_profile_is_saved_merged_and_available_to_catalog_and_local_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config_path = tmp_path / "config" / "custom_subjects.json"
            material_root = tmp_path / "law-materials"
            material_root.mkdir()
            (material_root / "讲义.txt").write_text("法学资料", encoding="utf-8")

            normalized = save_custom_subject_profile(
                {
                    "key": "law_398",
                    "catalog": {
                        "title": "398 法律硕士",
                        "subject_label": "法硕",
                        "status": "已启用",
                        "stage": "MVP",
                        "summary": "法硕资料知识点工作流。",
                        "capabilities": ["知识点抽取", "法条引用"],
                        "source_strategy": "本地讲义 + 结构化确认",
                        "notes": "测试自定义学科。",
                        "enabled": True,
                    },
                    "local_source": {
                        "key": "law_materials",
                        "title": "本地法硕资料",
                        "tab_label": "本地法硕资料",
                        "root_env_var": "LAW_MATERIAL_ROOT",
                        "fallback_dir_name": None,
                    },
                    "max_points": 18,
                    "extraction_guidance": "优先提取法条、构成要件与例外。",
                },
                custom_config_path=config_path,
            )

            self.assertEqual(normalized["key"], "law_398")
            self.assertTrue(config_path.is_file())
            self.assertEqual(list(config_path.parent.glob("*.tmp")), [])

            rag_profile = get_rag_knowledge_base_by_subject(
                "法硕", custom_config_path=config_path
            )
            self.assertIsNotNone(rag_profile)
            self.assertEqual(rag_profile.max_points, 18)
            self.assertEqual(rag_profile.extraction_guidance, "优先提取法条、构成要件与例外。")
            self.assertIn("法硕", list_enabled_subjects(custom_config_path=config_path))

            source_profile = get_local_material_source_for_subject(
                "法硕", custom_config_path=config_path
            )
            self.assertIsNotNone(source_profile)
            self.assertEqual(source_profile.key, "law_materials")
            with patch.dict(os.environ, {"LAW_MATERIAL_ROOT": str(material_root)}, clear=False):
                self.assertEqual(
                    get_local_material_root(
                        "law_materials", custom_config_path=config_path
                    ),
                    material_root.resolve(),
                )
                files = list_local_material_files(
                    "law_materials", custom_config_path=config_path
                )
                self.assertEqual(files[0]["relative_path"], "讲义.txt")

            with self.assertRaises(ValueError):
                save_custom_subject_profile(
                    {
                        "key": "exam_408",
                        "max_points": 20,
                        "extraction_guidance": "自定义 408 抽取指引。",
                    },
                    custom_config_path=config_path,
                )

            updated = save_custom_subject_profile(
                {
                    "key": "law_398",
                    "max_points": 20,
                    "extraction_guidance": "更新后的法硕抽取指引。",
                },
                custom_config_path=config_path,
            )
            self.assertEqual(updated["catalog"]["subject_label"], "法硕")
            overridden = get_rag_knowledge_base_by_subject(
                "法硕", custom_config_path=config_path
            )
            self.assertEqual(overridden.max_points, 20)
            self.assertEqual(overridden.extraction_guidance, "更新后的法硕抽取指引。")

    def test_bad_custom_config_safely_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "custom_subjects.json"
            config_path.write_text("{broken json", encoding="utf-8")

            profiles = list_rag_knowledge_bases(custom_config_path=config_path)

            self.assertEqual(len(profiles), 2)
            self.assertEqual(profiles[0].key, "exam_408")
            self.assertIn("历史学统考", list_enabled_subjects(custom_config_path=config_path))


if __name__ == "__main__":
    unittest.main()
