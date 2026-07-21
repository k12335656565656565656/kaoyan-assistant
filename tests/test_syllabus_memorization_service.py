import json
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from services.syllabus_memorization_service import (
    build_syllabus_expansion_prompt,
    generate_syllabus_memorization_points,
)


def _expanded_item(topic, *, suffix=""):
    return {
        "id": topic["id"],
        "core_definition": (
            f"{topic['knowledge_name']}是本专题需要掌握的核心内容{suffix}。"
            "需要依次说明时代背景、形成过程、主要内容、结果影响和历史地位，"
            "并能在材料题中结合时间线索、制度变化和社会条件组织答案。"
        ),
        "keywords": ["背景", "过程", "影响", "历史地位"],
        "related_concepts": ["时代背景", "制度演变"],
        "exam_question_styles": ["名词解释", "简答题"],
        "pitfalls": ["不要混淆时间顺序", "影响要分层作答"],
        "example_or_application": "按背景、过程、结果、影响四层组织答案。",
        "review_priority": "高",
    }


class SyllabusMemorizationServiceTests(unittest.TestCase):
    def test_generates_complete_history_memorization_points(self):
        calls = []

        def fake_llm(prompt):
            calls.append(prompt)
            if "背诵目录编辑" in prompt:
                return json.dumps(
                    [
                        {
                            "id": "k001",
                            "chapter_name": "中国古代史",
                            "knowledge_name": "商鞅变法",
                            "source_anchor": "商鞅变法",
                        },
                        {
                            "id": "k002",
                            "chapter_name": "中国近现代史",
                            "knowledge_name": "洋务运动",
                            "source_anchor": "洋务运动",
                        },
                        {
                            "id": "k003",
                            "chapter_name": "世界近现代史",
                            "knowledge_name": "工业革命",
                            "source_anchor": "工业革命",
                        },
                    ],
                    ensure_ascii=False,
                )
            topics = json.loads(prompt.split("待扩写条目：\n", 1)[1])
            return json.dumps([_expanded_item(topic) for topic in topics], ensure_ascii=False)

        progress = []
        points, warnings = generate_syllabus_memorization_points(
            "中国古代史：商鞅变法；中国近现代史：洋务运动；世界近现代史：工业革命。",
            subject="历史学基础",
            llm_callable=fake_llm,
            max_points=30,
            batch_size=2,
            max_workers=1,
            progress_callback=lambda current, total, message: progress.append(
                (current, total, message)
            ),
        )

        self.assertEqual(len(points), 3)
        self.assertEqual(warnings, [])
        self.assertEqual(
            {point["chapter_name"] for point in points},
            {"中国古代史", "中国近现代史", "世界近现代史"},
        )
        self.assertTrue(all(point["is_ai_expansion"] for point in points))
        self.assertTrue(all(len(point["core_definition"]) >= 60 for point in points))
        self.assertIn("历史类背诵材料", calls[1])
        self.assertNotIn("来源1", calls[1])
        self.assertIn("已生成 3 个背诵条目", progress[-1][2])

    def test_retries_a_missing_topic(self):
        expansion_calls = 0

        def fake_llm(prompt):
            nonlocal expansion_calls
            if "背诵目录编辑" in prompt:
                return json.dumps(
                    [
                        {"id": "same", "chapter_name": "第一章", "knowledge_name": "条目甲"},
                        {"id": "same", "chapter_name": "第一章", "knowledge_name": "条目乙"},
                    ],
                    ensure_ascii=False,
                )
            expansion_calls += 1
            topics = json.loads(prompt.split("待扩写条目：\n", 1)[1])
            selected = topics[:1] if expansion_calls == 1 else topics
            return json.dumps([_expanded_item(topic) for topic in selected], ensure_ascii=False)

        points, warnings = generate_syllabus_memorization_points(
            "第一章包括条目甲和条目乙。",
            subject="历史学基础",
            llm_callable=fake_llm,
            max_points=10,
            batch_size=5,
            max_workers=1,
        )

        self.assertEqual(expansion_calls, 2)
        self.assertEqual({point["knowledge_name"] for point in points}, {"条目甲", "条目乙"})
        self.assertEqual(warnings, [])

    def test_rejects_empty_syllabus(self):
        with self.assertRaisesRegex(ValueError, "没有可读取"):
            generate_syllabus_memorization_points(
                "",
                subject="历史学基础",
                llm_callable=lambda prompt: "[]",
            )

    def test_expansion_prompt_requests_direct_content_only(self):
        prompt = build_syllabus_expansion_prompt(
            [{"id": "k001", "chapter_name": "中国古代史", "knowledge_name": "秦朝统一"}],
            subject="历史学基础",
        )
        self.assertIn("不要 Markdown、前言、来源编号、页码、思考过程", prompt)
        self.assertIn("直接写知识内容", prompt)


if __name__ == "__main__":
    unittest.main()
