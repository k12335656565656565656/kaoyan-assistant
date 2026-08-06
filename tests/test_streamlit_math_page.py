import unittest

from personalized_learning.streamlit_page import (
    _inject_exam_goal_styles,
    format_question_metadata,
    format_knowledge_point_tags,
    format_knowledge_catalog_markup,
    split_question_content,
)


class StreamlitMathPageTests(unittest.TestCase):
    def test_math_choice_group_uses_flat_two_column_layout(self):
        class FakeStreamlit:
            def __init__(self):
                self.markdowns = []

            def markdown(self, value, **kwargs):
                self.markdowns.append(value)

        st = FakeStreamlit()

        _inject_exam_goal_styles(st)

        styles = "\n".join(st.markdowns)
        self.assertIn("st-key-math_pool_answer_", styles)
        self.assertIn("grid-template-columns:repeat(2,minmax(0,1fr))", styles)
        self.assertIn("background:transparent", styles)

    def test_splits_inline_multiple_choice_options_from_the_stem(self):
        stem, options = split_question_content(
            "设数列 {x_n} 收敛，则下列正确的是 A) 选项一 B) 选项二 C) 选项三 D) 选项四"
        )

        self.assertEqual(stem, "设数列 {x_n} 收敛，则下列正确的是")
        self.assertEqual(options, {
            "A": "选项一",
            "B": "选项二",
            "C": "选项三",
            "D": "选项四",
        })

    def test_question_metadata_exposes_all_knowledge_point_tags(self):
        self.assertEqual(
            format_knowledge_point_tags(("001-数列极限的定义与性质.md", "064-多元函数微分学.md")),
            ("数列极限的定义与性质", "多元函数微分学"),
        )

    def test_labels_variant_source_and_knowledge_points_without_calling_it_a_true_question(self):
        metadata = format_question_metadata(
            year=2026,
            difficulty_tier="基础",
            mapping_status="ai_suggested",
            knowledge_point_ids=("064-多元函数微分学.md",),
        )

        self.assertIn("真题变式", metadata["source"])
        self.assertNotIn("2026 年真题", metadata["source"])
        self.assertEqual(metadata["knowledge_points"], "多元函数微分学")

    def test_labels_provisional_screenshot_mapping_as_a_true_exam(self):
        metadata = format_question_metadata(
            year=2025,
            difficulty_tier="基础",
            mapping_status="ai_suggested",
            knowledge_point_ids=("031-特征值与特征向量.md",),
            source_reference="2025/math1/pdf_page_0001.png",
        )

        self.assertEqual(metadata["source"], "2025 年真题")

    def test_formats_complete_knowledge_catalog_as_a_compact_grid(self):
        markup = format_knowledge_catalog_markup((
            {"id": "001-极限.md", "text": "数列极限"},
            {"id": "002-连续.md", "text": "函数连续性"},
        ))

        self.assertIn("eg-knowledge-catalog", markup)
        self.assertIn("001", markup)
        self.assertIn("极限", markup)
        self.assertIn("002", markup)
        self.assertNotIn(" · ", markup)


if __name__ == "__main__":
    unittest.main()
