import unittest

from personalized_learning.math.diagnosis import build_diagnosis_plan
from personalized_learning.math.diagnosis_variants import build_variant_batch_prompt, build_variant_questions
from personalized_learning.models import ExamQuestion
from personalized_learning.repository import ensure_schema, import_exam_questions, list_diagnostic_questions
import sqlite3


def reference_question():
    return ExamQuestion(
        question_id="math1:2026:1:v1",
        exam_type="math1",
        year=2026,
        question_no="1",
        section="选择题",
        score=4,
        difficulty_coefficient=0.8,
        question_text="原始真题",
        answer="A",
        explanation="原始解析",
        knowledge_point_ids=("limit",),
        source_reference="2026 数学一真题",
        mapping_status="confirmed",
    )


class DiagnosisVariantTests(unittest.TestCase):
    def test_builds_traceable_ai_suggested_variants_from_batch_output(self):
        plan = build_diagnosis_plan(("limit",), question_count=2)
        raw = """Q: 当 $x$ 趋于 0 时，以下极限正确的是？
A) 0
B) 1
C) 2
D) 不存在
ANSWER: B
EXPLAIN: 使用基本极限。
---
Q: 设函数在 0 点可导，则下列判断正确的是？
A) 连续
B) 发散
C) 无界
D) 不确定
ANSWER: A
EXPLAIN: 可导必连续。
---"""

        variants = build_variant_questions(raw, plan, (reference_question(),))

        self.assertEqual(len(variants), 2)
        self.assertEqual(variants[0].mapping_status, "ai_suggested")
        self.assertEqual(variants[0].knowledge_point_ids, ("limit",))
        self.assertIn("ai_variant:math1:2026:1:v1", variants[0].source_reference)
        self.assertEqual(variants[1].difficulty_tier, "标准")

    def test_discards_incomplete_variant_blocks(self):
        plan = build_diagnosis_plan(("limit",), question_count=1)
        raw = "Q: 缺少答案的题目\nA) 0\nB) 1\n---"

        self.assertEqual(build_variant_questions(raw, plan, (reference_question(),)), ())

    def test_provisional_variants_can_be_loaded_for_diagnosis_without_entering_true_question_weights(self):
        connection = sqlite3.connect(":memory:")
        ensure_schema(connection)
        variant = build_variant_questions(
            "Q: 测试变式题\nA) 0\nB) 1\nC) 2\nD) 3\nANSWER: B\nEXPLAIN: 测试解析\n---",
            build_diagnosis_plan(("limit",), question_count=1),
            (reference_question(),),
        )[0]
        import_exam_questions(connection, [variant], data_version="generated-v1")

        self.assertEqual(list_diagnostic_questions(connection, "math1"), [variant])

    def test_batch_prompt_limits_the_model_to_the_missing_diagnosis_slots(self):
        plan = build_diagnosis_plan(("limit",), question_count=2)
        prompt = build_variant_batch_prompt(plan, (reference_question(),))

        self.assertIn("共 2 道", prompt)
        self.assertIn("math1:2026:1:v1", prompt)
        self.assertIn("不得输出思考过程", prompt)

    def test_batch_prompt_keeps_every_reference_when_building_a_small_diagnosis_batch(self):
        references = tuple(
            reference_question().__class__(**{**reference_question().__dict__, "question_id": f"ref-{index}", "question_no": str(index)})
            for index in range(10)
        )
        prompt = build_variant_batch_prompt(build_diagnosis_plan(("limit",), question_count=1), references)

        self.assertIn("ref-9", prompt)


if __name__ == "__main__":
    unittest.main()
