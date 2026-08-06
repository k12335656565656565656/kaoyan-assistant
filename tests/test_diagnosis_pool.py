import unittest

from personalized_learning.math.diagnosis import build_diagnosis_plan
from personalized_learning.math import diagnosis_pool
from personalized_learning.math.diagnosis_pool import select_diagnosis_questions, variant_slots_to_generate
from personalized_learning.models import ExamQuestion


def make_question(question_id, knowledge_id, coefficient, year=2026):
    return ExamQuestion(
        question_id=question_id,
        exam_type="math1",
        year=year,
        question_no=question_id,
        section="选择题",
        score=4,
        difficulty_coefficient=coefficient,
        question_text=f"题目 {question_id}",
        answer="A",
        explanation="解析",
        knowledge_point_ids=(knowledge_id,),
        source_reference="真题",
        mapping_status="confirmed",
    )


def make_provisional_question(question_id, knowledge_id, coefficient, source_reference, year=2026):
    question = make_question(question_id, knowledge_id, coefficient, year)
    return question.__class__(
        **{
            **question.__dict__,
            "mapping_status": "ai_suggested",
            "source_reference": source_reference,
        }
    )


def make_multi_question(question_id, knowledge_ids, coefficient, year=2026):
    return ExamQuestion(
        question_id=question_id,
        exam_type="math1",
        year=year,
        question_no=question_id,
        section="閫夋嫨棰?",
        score=4,
        difficulty_coefficient=coefficient,
        question_text=f"棰樼洰 {question_id}",
        answer="A",
        explanation="瑙ｆ瀽",
        knowledge_point_ids=tuple(knowledge_ids),
        source_reference="鐪熼",
        mapping_status="confirmed",
    )


class DiagnosisPoolTests(unittest.TestCase):
    def test_selects_mapped_questions_by_plan_knowledge_and_difficulty(self):
        plan = build_diagnosis_plan(("limit", "matrix"), question_count=3)
        questions = (
            make_question("limit-basic", "limit", 0.8),
            make_question("matrix-basic", "matrix", 0.8),
            make_question("limit-standard", "limit", 0.55),
        )

        result = select_diagnosis_questions(plan, questions)

        self.assertEqual([item.question_id for item in result.questions], [
            "limit-basic", "matrix-basic", "limit-standard",
        ])
        self.assertEqual(result.uncovered_plan_indexes, ())

    def test_reuses_bank_questions_for_a_new_diagnosis_but_not_twice_in_one_batch(self):
        plan = build_diagnosis_plan(("limit",), question_count=2)
        questions = (
            make_question("limit-basic", "limit", 0.8),
            make_question("limit-standard", "limit", 0.55),
        )

        result = select_diagnosis_questions(plan, questions, prior_question_ids=("limit-basic",))

        self.assertEqual(len(result.questions), 2)
        self.assertEqual(len({item.question_id for item in result.questions}), 2)
        self.assertEqual(result.questions[0].question_id, "limit-basic")

    def test_reports_uncovered_plan_items_when_the_confirmed_bank_is_insufficient(self):
        plan = build_diagnosis_plan(("limit", "matrix"), question_count=2)
        result = select_diagnosis_questions(plan, (make_question("limit-basic", "limit", 0.8),))

        self.assertEqual([item.question_id for item in result.questions], ["limit-basic"])
        self.assertEqual(result.uncovered_plan_indexes, (1,))

    def test_can_include_provisional_variants_when_explicitly_enabled(self):
        plan = build_diagnosis_plan(("limit",), question_count=1)
        variant = make_question("variant-limit", "limit", 0.8)
        variant = variant.__class__(**{**variant.__dict__, "mapping_status": "ai_suggested"})

        result = select_diagnosis_questions(
            plan,
            (variant,),
            allowed_mapping_statuses=("confirmed", "ai_suggested"),
        )

        self.assertEqual(result.questions, (variant,))

    def test_fills_a_diagnosis_batch_but_keeps_sparse_point_marked_uncovered(self):
        plan = build_diagnosis_plan(("limit", "matrix"), question_count=2)
        questions = (
            make_question("limit-basic", "limit", 0.8),
            make_question("integral-basic", "integral", 0.8),
        )

        result = select_diagnosis_questions(plan, questions)

        self.assertEqual(
            [item.question_id for item in result.questions],
            ["limit-basic", "integral-basic"],
        )
        self.assertEqual(result.uncovered_plan_indexes, (1,))

    def test_can_mix_multiple_true_exam_years_with_ai_variants_for_diagnosis(self):
        plan = build_diagnosis_plan(("limit",), question_count=4)
        questions = (
            make_question("real-2026", "limit", 0.8, 2026),
            make_question("real-2024", "limit", 0.55, 2024),
            make_question("variant-1", "limit", 0.8, 2026).__class__(
                **{**make_question("variant-1", "limit", 0.8, 2026).__dict__, "mapping_status": "ai_suggested"}
            ),
            make_question("variant-2", "limit", 0.55, 2026).__class__(
                **{**make_question("variant-2", "limit", 0.55, 2026).__dict__, "mapping_status": "ai_suggested"}
            ),
        )

        result = select_diagnosis_questions(
            plan,
            questions,
            allowed_mapping_statuses=("confirmed", "ai_suggested"),
            true_question_ratio=0.5,
        )

        self.assertEqual(len(result.questions), 4)
        self.assertEqual({item.mapping_status for item in result.questions}, {"confirmed", "ai_suggested"})
        self.assertEqual({item.year for item in result.questions if item.mapping_status == "confirmed"}, {2024, 2026})

    def test_uses_source_kind_for_the_true_exam_ratio_when_mapping_is_provisional(self):
        plan = build_diagnosis_plan(("limit",), question_count=2)
        real = make_provisional_question("real-2025", "limit", 0.8, "2025/math1/pdf_page_0001.png", 2025)
        variant = make_provisional_question("variant-1", "limit", 0.8, "ai_variant:knowledge_base", 2026)

        result = select_diagnosis_questions(
            plan,
            (real, variant),
            allowed_mapping_statuses=("confirmed", "ai_suggested"),
            true_question_ratio=0.5,
        )

        self.assertEqual({item.question_id for item in result.questions}, {"real-2025", "variant-1"})
        self.assertEqual(sum(item.is_true_exam for item in result.questions), 1)

    def test_never_selects_a_question_without_a_knowledge_mapping(self):
        plan = build_diagnosis_plan(("matrix",), question_count=1)
        untagged = make_provisional_question("a-untagged", "limit", 0.8, "2025/math1/page.png")
        untagged = untagged.__class__(**{**untagged.__dict__, "knowledge_point_ids": ()})

        result = select_diagnosis_questions(
            plan,
            (untagged,),
            allowed_mapping_statuses=("confirmed", "ai_suggested"),
        )

        self.assertEqual(result.questions, ())
        self.assertEqual(result.uncovered_plan_indexes, (0,))

    def test_reports_missing_variant_slots_even_when_the_real_bank_has_enough_questions(self):
        plan = build_diagnosis_plan(("limit",), question_count=5)
        questions = tuple(make_question(f"real-{index}", "limit", 0.8, year=2021 + index) for index in range(5))
        selection = select_diagnosis_questions(
            plan,
            questions,
            allowed_mapping_statuses=("confirmed",),
            true_question_ratio=0.6,
        )

        slots = variant_slots_to_generate(plan, selection, true_question_ratio=0.6)

        self.assertEqual(slots, ())

    def test_diagnosis_generation_slots_waits_only_for_an_incomplete_local_batch(self):
        plan = build_diagnosis_plan(("limit",), question_count=5)
        questions = tuple(make_question(f"real-{index}", "limit", 0.8, year=2021 + index) for index in range(5))
        selection = select_diagnosis_questions(
            plan,
            questions,
            allowed_mapping_statuses=("confirmed",),
            true_question_ratio=0.6,
        )

        slots_builder = getattr(diagnosis_pool, "diagnosis_generation_slots", None)
        self.assertIsNotNone(slots_builder)
        self.assertEqual(slots_builder(plan, selection, true_question_ratio=0.6), ())

    def test_coverage_mode_selects_twenty_questions_that_maximize_all_tags(self):
        plan = build_diagnosis_plan(("limit",), question_count=3)
        questions = (
            make_multi_question("q-a", ("a",), 0.8),
            make_multi_question("q-bc", ("b", "c"), 0.55),
            make_multi_question("q-d", ("d",), 0.2),
            make_multi_question("q-ad", ("a", "d"), 0.8),
        )

        result = select_diagnosis_questions(
            plan,
            questions,
            coverage_knowledge_point_ids=("a", "b", "c", "d"),
        )

        self.assertEqual(len(result.questions), 3)
        self.assertEqual(
            {tag for question in result.questions for tag in question.knowledge_point_ids},
            {"a", "b", "c", "d"},
        )
        self.assertEqual(result.uncovered_knowledge_point_ids, ())

    def test_coverage_mode_reports_tags_missing_from_the_question_bank(self):
        plan = build_diagnosis_plan(("limit",), question_count=1)
        result = select_diagnosis_questions(
            plan,
            (make_multi_question("q-a", ("a",), 0.8),),
            coverage_knowledge_point_ids=("a", "missing"),
        )

        self.assertEqual(result.uncovered_knowledge_point_ids, ("missing",))


if __name__ == "__main__":
    unittest.main()
