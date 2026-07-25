import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from professional_knowledge.builtin_history import (
    BUILTIN_HISTORY_EXAM_SUBJECTS,
    BUILTIN_HISTORY_SOURCE_TYPE,
    ensure_builtin_history_points,
    load_builtin_history_points,
)
from professional_knowledge.catalog import (
    list_rag_knowledge_bases,
    set_subject_enabled,
)
from repositories.knowledge_repo import list_user_knowledge_points
from repositories.user_subject_repo import (
    list_user_subject_profiles,
    save_user_subject_profile,
)
from services.professional_question_prompts import (
    build_minimal_professional_question_prompt,
    build_professional_question_prompt,
    is_history_knowledge_point,
)
from services.professional_question_validator import (
    is_valid_professional_question_for_point,
)
from scripts.build_history_knowledge_base import _clean_text


class BuiltinSubjectRegistryTests(unittest.TestCase):
    def _history_points_or_skip(self):
        points = list(load_builtin_history_points())
        if not points:
            self.skipTest("optional private 313 knowledge catalog is not installed")
        return points

    def test_default_catalog_contains_exactly_two_fixed_enabled_subjects(self):
        profiles = list_rag_knowledge_bases(custom_config_path=Path("missing.json"))
        enabled = [profile for profile in profiles if profile.enabled]
        self.assertEqual(
            [(profile.key, profile.subject_label) for profile in enabled],
            [
                ("exam_408", "408综合"),
                ("exam_history_313", "历史学统考"),
            ],
        )
        self.assertTrue(all(profile.fixed for profile in enabled))

    def test_custom_config_cannot_override_or_duplicate_fixed_subjects(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "custom_subjects.json"
            path.write_text(
                json.dumps(
                    {
                        "subjects": [
                            {
                                "key": "exam_408",
                                "catalog": {"enabled": False},
                            },
                            {
                                "key": "fake_408",
                                "catalog": {
                                    "title": "重复408",
                                    "subject_label": "408",
                                    "status": "自定义",
                                    "stage": "自定义",
                                    "summary": "",
                                    "capabilities": [],
                                    "source_strategy": "",
                                    "notes": "",
                                    "enabled": True,
                                },
                            },
                            {
                                "key": "custom_law",
                                "catalog": {
                                    "title": "法学基础",
                                    "subject_label": "法学基础",
                                    "status": "自定义",
                                    "stage": "自定义",
                                    "summary": "",
                                    "capabilities": [],
                                    "source_strategy": "",
                                    "notes": "",
                                    "enabled": True,
                                },
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            profiles = list_rag_knowledge_bases(custom_config_path=path)
        by_label = {profile.subject_label: profile for profile in profiles}
        self.assertTrue(by_label["408综合"].enabled)
        self.assertTrue(by_label["408综合"].fixed)
        self.assertNotIn("408", by_label)
        self.assertIn("法学基础", by_label)

    def test_fixed_subject_cannot_be_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "custom_subjects.json"
            with self.assertRaisesRegex(ValueError, "固定专业课"):
                set_subject_enabled("exam_408", False, custom_config_path=path)

    def test_history_catalog_is_deployable_and_covers_four_exam_subjects(self):
        points = self._history_points_or_skip()
        self.assertGreaterEqual(len(points), 250)
        self.assertEqual(
            set(BUILTIN_HISTORY_EXAM_SUBJECTS),
            {point["chapter_name"] for point in points},
        )
        serialized = json.dumps(points, ensure_ascii=False)
        self.assertNotIn("General Examination in History", serialized)
        self.assertNotRegex(serialized, r"[A-Za-z]:\\\\")
        self.assertTrue(all(point.get("knowledge_name") for point in points))
        self.assertTrue(all(point.get("core_definition") for point in points))
        self.assertLessEqual(max(len(point.get("source_text") or "") for point in points), 1300)
        self.assertLessEqual(max(len(point.get("core_definition") or "") for point in points), 1250)
        self.assertTrue(
            all("**1. 历史定位**" in point["core_definition"] for point in points)
        )
        self.assertTrue(
            all("**2. 核心要点**" in point["core_definition"] for point in points)
        )

    def test_history_core_content_stops_before_unrelated_sibling_sections(self):
        point = next(
            point
            for point in self._history_points_or_skip()
            if point["knowledge_name"] == "三国鼎立"
        )
        content = point["core_definition"]
        self.assertIn("**2.1 三次战争**", content)
        self.assertIn("**2.2 原因**", content)
        self.assertIn("**2.3 意义**", content)
        self.assertNotIn("九品中正", content)
        self.assertNotIn("【复习线索】", content)
        self.assertNotIn("【作答框架】", content)

    def test_history_generic_culture_heading_uses_complete_era_title(self):
        points = self._history_points_or_skip()
        point = next(
            point
            for point in points
            if point["source_location"].endswith("> 文化")
            and "魏晋" in point["source_location"]
        )

        self.assertEqual(point["knowledge_name"], "魏晋南北朝文化")
        self.assertIn(
            "三国（—265）魏晋（265-318-420）南北朝（420-589）",
            point["core_definition"],
        )
        self.assertNotIn("420-5 · 文化", point["core_definition"])

    def test_history_titles_have_balanced_chinese_parentheses(self):
        points = self._history_points_or_skip()
        malformed = [
            point["knowledge_name"]
            for point in points
            if point["knowledge_name"].count("（")
            != point["knowledge_name"].count("）")
        ]

        self.assertEqual(malformed, [])
        self.assertTrue(
            any(
                point["knowledge_name"] == "总结民国初年（北洋政府）"
                for point in points
            )
        )

    def test_history_catalog_removes_source_artifacts_and_confirmed_typos(self):
        points = self._history_points_or_skip()
        combined = "\n".join(point["core_definition"] for point in points)
        for artifact in ("★", "🌟", "\ufffd", "•"):
            self.assertNotIn(artifact, combined)
        self.assertNotIn("东汉以来门阀士族势力恶性膨胀的", combined)

        point = next(
            point
            for point in points
            if point["knowledge_name"] == "中央制度演化"
        )
        content = point["core_definition"]
        for typo in ("秦朗", "牵剖", "决断杖", "中框", " > "):
            self.assertNotIn(typo, content)
        for correction in ("秦朝", "互相牵制", "决策权", "中枢"):
            self.assertIn(correction, content)
        self.assertNotRegex(content, r"[,，；]\s*他(?:\n|$)")

    def test_history_outline_headings_do_not_end_mid_sentence(self):
        points = self._history_points_or_skip()
        combined = "\n".join(point["core_definition"] for point in points)
        for broken_fragment in (
            "东汉以来门阀士族势力恶性膨胀的",
            "思想家的学说影**",
            "毕达哥拉斯认为抽象的**",
            "哲•学家",
        ):
            self.assertNotIn(broken_fragment, combined)

    def test_history_catalog_can_seed_sqlite_without_source_docx(self):
        points_to_seed = self._history_points_or_skip()
        conn = sqlite3.connect(":memory:")
        try:
            saved = ensure_builtin_history_points(conn, 7, "历史学统考")
            conn.commit()
            points = list_user_knowledge_points(
                conn, 7, limit=1000, subject="历史学统考"
            )
        finally:
            conn.close()
        self.assertEqual(saved, len(points_to_seed))
        self.assertEqual(len(points), len(points_to_seed))
        self.assertEqual({BUILTIN_HISTORY_SOURCE_TYPE}, {p["source_type"] for p in points})

    def test_missing_private_history_catalog_is_non_blocking(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing-history-catalog.json"
            self.assertEqual(load_builtin_history_points(missing), ())
            conn = sqlite3.connect(":memory:")
            try:
                saved = ensure_builtin_history_points(
                    conn,
                    7,
                    "历史学统考",
                    catalog_path=missing,
                )
            finally:
                conn.close()
        self.assertEqual(saved, 0)

    def test_history_cleaner_removes_embedded_course_page_headers(self):
        dirty = (
            "包括中国古代史强化教程329《新唐书》，"
            "以及世界史古代中世纪史强化教程 63 奥林匹亚诸神。"
        )
        cleaned = _clean_text(dirty)
        self.assertEqual(cleaned, "包括《新唐书》，以及奥林匹亚诸神。")

    def test_custom_subject_profiles_are_isolated_by_user(self):
        conn = sqlite3.connect(":memory:")
        profile = {
            "key": "custom_management",
            "catalog": {
                "title": "803 管理学原理",
                "subject_label": "管理学原理",
                "status": "已启用",
                "stage": "自定义",
                "summary": "",
                "capabilities": ["资料导入"],
                "source_strategy": "",
                "notes": "",
                "enabled": True,
            },
            "local_source": None,
            "max_points": 12,
            "exam_subjects": ["管理学原理"],
            "extraction_guidance": "",
        }
        try:
            save_user_subject_profile(conn, 1, profile)
            conn.commit()
            user_one = list_user_subject_profiles(conn, 1)
            user_two = list_user_subject_profiles(conn, 2)
        finally:
            conn.close()
        self.assertEqual([item["key"] for item in user_one], ["custom_management"])
        self.assertEqual(user_two, [])

    def test_user_subject_repository_rejects_fixed_subject_alias(self):
        conn = sqlite3.connect(":memory:")
        profile = {
            "key": "fake_408",
            "catalog": {
                "title": "重复课程",
                "subject_label": "408",
                "status": "已启用",
                "stage": "自定义",
                "summary": "",
                "capabilities": [],
                "source_strategy": "",
                "notes": "",
                "enabled": True,
            },
            "max_points": 12,
            "exam_subjects": ["数据结构"],
            "extraction_guidance": "",
        }
        try:
            with self.assertRaisesRegex(ValueError, "固定专业课"):
                save_user_subject_profile(conn, 1, profile)
        finally:
            conn.close()

    def test_history_prompts_are_decoupled_from_408(self):
        point = {
            "subject": "历史学统考",
            "chapter_name": "中国近现代史",
            "knowledge_name": "洋务运动",
            "core_definition": "19世纪60至90年代的自强、求富运动。",
            "source_type": BUILTIN_HISTORY_SOURCE_TYPE,
        }
        self.assertTrue(is_history_knowledge_point(point))
        for prompt in (
            build_professional_question_prompt(point, "application", 1),
            build_minimal_professional_question_prompt(point, "concept", 2),
        ):
            self.assertIn("313历史学统考", prompt)
            self.assertNotIn("408命题老师", prompt)
            self.assertNotIn("408考研", prompt)

    def test_history_validator_rejects_vague_question(self):
        point = {
            "subject": "历史学统考",
            "chapter_name": "中国近现代史",
            "knowledge_name": "洋务运动",
            "source_type": BUILTIN_HISTORY_SOURCE_TYPE,
        }
        vague = {
            "question": "请谈谈你对历史的感想，并说明学习历史为什么重要。",
            "options": [],
            "correct_answer": "",
            "reference_answer": "历史具有重要意义，应当认真学习。",
            "grading_points": ["意义"],
        }
        self.assertFalse(
            is_valid_professional_question_for_point(
                vague, "application", point=point
            )
        )


if __name__ == "__main__":
    unittest.main()
