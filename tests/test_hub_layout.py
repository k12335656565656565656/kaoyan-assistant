import re
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


class HubLayoutTests(unittest.TestCase):
    def test_home_module_cards_define_a_shared_height(self):
        source = (PROJECT_DIR / "app.py").read_text(encoding="utf-8")

        card_css = re.search(
            r"\.hub-feature-card\s*\{(?P<body>.*?)\}",
            source,
            flags=re.DOTALL,
        )

        self.assertIsNotNone(card_css, "首页模块卡片需要独立的等高布局规则")
        self.assertRegex(
            card_css.group("body"),
            r"\bheight\s*:\s*\d+px",
            "首页模块卡片需要固定高度，才能让各列的进入按钮共用基线",
        )
        self.assertIn("class=\"feature-card hub-feature-card\"", source)

    def test_math_knowledge_quiz_reuses_professional_style_generation_feedback(self):
        source = (PROJECT_DIR / "app.py").read_text(encoding="utf-8")

        self.assertIn("def _render_math_question_progress", source)
        self.assertIn(
            '_render_math_question_progress(quiz_progress, "request_started")',
            source,
        )
        self.assertIsNotNone(
            re.search(
                r"\.math-question-progress\s*\{.*?min-height:\s*112px",
                source,
                flags=re.DOTALL,
            ),
            "数学出题进度组件需要保持与题目区域协调的稳定高度",
        )


if __name__ == "__main__":
    unittest.main()
