import unittest

from personalized_learning.models import MasterySnapshot
from personalized_learning.streamlit_page import (
    _render_requirement_group,
    _training_requirement_labels,
    choose_diagnosis_knowledge_points,
    count_diagnosis_questions,
    generate_training_material_content,
    parse_generated_quiz,
)
from personalized_learning.models import PersonalizedRequirement
from personalized_learning.training.material_generator import build_training_material_request


class MathPersonalizationPageTests(unittest.TestCase):
    def test_requirement_display_order_is_priority_first(self):
        class FakeStreamlit:
            def __init__(self):
                self.markdowns = []

            def markdown(self, value, **kwargs):
                self.markdowns.append(value)

            def caption(self, value):
                pass

        requirements = [
            type("Requirement", (), {"knowledge_point_id": "low", "priority": 0.4, "tier": "基础", "mastery": 0.2, "target_mastery": 0.8, "reason": "low"})(),
            type("Requirement", (), {"knowledge_point_id": "high", "priority": 2.8, "tier": "标准", "mastery": 0.2, "target_mastery": 0.8, "reason": "high"})(),
            type("Requirement", (), {"knowledge_point_id": "middle", "priority": 1.2, "tier": "提高", "mastery": 0.2, "target_mastery": 0.8, "reason": "middle"})(),
        ]
        st = FakeStreamlit()

        _render_requirement_group(st, requirements)

        rendered = "\n".join(st.markdowns)
        self.assertLess(rendered.find("high"), rendered.find("low"))

    def test_generated_quiz_parser_keeps_options_answer_and_explanation(self):
        parsed = parse_generated_quiz(
            "Q: 函数极限题\nA) 0\nB) 1\nC) 2\nD) 3\nANSWER: B\nEXPLAIN: 根据极限定义。"
        )

        self.assertEqual(parsed["answer"], "B")
        self.assertEqual(len(parsed["options"]), 4)
        self.assertIn("极限定义", parsed["explain"])

    def test_diagnosis_picker_prefers_weak_points_then_unseen_points(self):
        knowledge_points = [
            {"id": "limit", "name": "极限"},
            {"id": "matrix", "name": "矩阵"},
            {"id": "probability", "name": "概率"},
        ]
        snapshots = {
            "matrix": MasterySnapshot("matrix", 0.2, 0, 2, 0.0, 3, 0.0),
            "limit": MasterySnapshot("limit", 0.8, 2, 0, 1.0, 8, 0.0),
        }

        selected = choose_diagnosis_knowledge_points(knowledge_points, snapshots, limit=2)
        self.assertEqual(selected, ("matrix", "probability"))

    def test_diagnosis_progress_counts_distinct_questions(self):
        evidence = [
            type("Evidence", (), {"question_id": "diagnosis-1", "source": "diagnosis"})(),
            type("Evidence", (), {"question_id": "diagnosis-1", "source": "diagnosis"})(),
            type("Evidence", (), {"question_id": "exam-1", "source": "exam"})(),
        ]
        self.assertEqual(count_diagnosis_questions(evidence), 1)

    def test_requirement_group_renders_all_available_knowledge_points(self):
        class FakeStreamlit:
            def __init__(self):
                self.markdowns = []

            def markdown(self, value, **kwargs):
                self.markdowns.append(value)

            def caption(self, value):
                pass

        requirements = [
            type(
                "Requirement",
                (),
                {
                    "knowledge_point_id": f"kp-{index}",
                    "mastery": 0.35,
                    "target_mastery": 0.8,
                    "priority": 1.0,
                    "reason": "待补",
                },
            )()
            for index in range(10)
        ]
        st = FakeStreamlit()

        _render_requirement_group(st, requirements)

        self.assertEqual(len(st.markdowns), 10)

    def test_requirement_group_uses_compact_grid_and_collapses_overflow(self):
        class FakeExpander:
            def __init__(self, owner, label):
                self.owner = owner
                self.label = label

            def __enter__(self):
                self.owner.expander_labels.append(self.label)
                return self.owner

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        class FakeStreamlit:
            def __init__(self):
                self.markdowns = []
                self.expander_labels = []

            def markdown(self, value, **kwargs):
                self.markdowns.append(value)

            def caption(self, value):
                pass

            def expander(self, label, expanded=False):
                return FakeExpander(self, label)

        requirements = [
            type(
                "Requirement",
                (),
                {
                    "knowledge_point_id": f"kp-{index}",
                    "mastery": 0.35,
                    "target_mastery": 0.8,
                    "priority": 10 - index,
                    "tier": "基础",
                    "reason": "待补",
                },
            )()
            for index in range(10)
        ]
        st = FakeStreamlit()

        _render_requirement_group(st, requirements)

        self.assertIn("eg-requirement-grid", st.markdowns[0])
        self.assertIn("01", st.markdowns[0])
        self.assertEqual(st.expander_labels, ["查看全部 10 项"])

    def test_training_labels_make_priority_order_visible(self):
        requirements = [
            type("Requirement", (), {"knowledge_point_id": "low", "tier": "基础", "priority": 0.4})(),
            type("Requirement", (), {"knowledge_point_id": "high", "tier": "标准", "priority": 2.8})(),
        ]

        labels = _training_requirement_labels(requirements)

        self.assertEqual(labels[0], "01 · high · 标准 · 优先级 2.80")
        self.assertEqual(labels[1], "02 · low · 基础 · 优先级 0.40")

    def test_training_material_generation_returns_content_and_prompt_context(self):
        requirement = PersonalizedRequirement(
            knowledge_point_id="limit",
            tier="基础",
            mastery=0.2,
            target_mastery=0.8,
            gap=0.6,
            expected_contribution=5.0,
            priority=2.0,
            forgetting_risk=0.3,
            reason="近期错误较多",
            evidence_summary={"times_wrong": 2},
        )
        request = build_training_material_request(requirement)
        prompts = []

        def generator(prompt):
            prompts.append(prompt)
            return "# 核心定义\n极限的定义"

        content, error = generate_training_material_content(generator, request, "极限知识点原文")

        self.assertEqual(error, "")
        self.assertEqual(content, "# 核心定义\n极限的定义")
        self.assertIn("极限知识点原文", prompts[0])

    def test_training_material_generation_converts_failures_to_user_visible_error(self):
        requirement = PersonalizedRequirement(
            knowledge_point_id="limit",
            tier="基础",
            mastery=0.2,
            target_mastery=0.8,
            gap=0.6,
            expected_contribution=5.0,
            priority=2.0,
            forgetting_risk=0.3,
            reason="近期错误较多",
        )
        request = build_training_material_request(requirement)

        content, error = generate_training_material_content(
            lambda prompt: (_ for _ in ()).throw(RuntimeError("HTTP 402")),
            request,
            "极限知识点原文",
        )

        self.assertEqual(content, "")
        self.assertIn("HTTP 402", error)

    def test_training_material_generation_explains_local_socket_permission_error(self):
        requirement = PersonalizedRequirement(
            knowledge_point_id="limit",
            tier="基础",
            mastery=0.2,
            target_mastery=0.8,
            gap=0.6,
            expected_contribution=5.0,
            priority=2.0,
            forgetting_risk=0.3,
            reason="近期错误较多",
        )
        request = build_training_material_request(requirement)

        content, error = generate_training_material_content(
            lambda prompt: (_ for _ in ()).throw(PermissionError(10013, "blocked")),
            request,
            "极限知识点原文",
        )

        self.assertEqual(content, "")
        self.assertIn("Windows 防火墙", error)
        self.assertIn("10013", error)


if __name__ == "__main__":
    unittest.main()
