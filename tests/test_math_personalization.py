import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from personalized_learning.math.diagnosis import build_diagnosis_plan, has_completed_diagnosis, record_diagnosis_answer
from personalized_learning.math.generator import (
    adapt_existing_review_generator,
    generate_diagnosis_questions,
)
from personalized_learning.math.mastery import calculate_mastery
from personalized_learning.math.requirements import (
    build_diagnostic_requirements,
    build_requirements,
)
from personalized_learning.math.selector import select_next_question
from personalized_learning.models import (
    ExamQuestion,
    MasteryEvidence,
    StudentProfile,
    classify_difficulty,
)
from personalized_learning.repository import (
    ensure_schema,
    confirm_question_mapping,
    get_profile,
    get_legacy_math_exam_type,
    get_mastery_snapshots,
    import_exam_questions,
    list_diagnostic_questions,
    list_eligible_exam_questions,
    load_exam_question_rows,
    save_evidence,
    save_profile,
    suggest_question_mapping,
    repair_legacy_question_mapping_ids,
)
from personalized_learning.streamlit_page import EXAM_TYPES, resolve_math_exam_type
from personalized_learning.streamlit_page import is_math_answer_correct
from personalized_learning.training.material_generator import build_training_material_request


def make_question(
    question_id,
    knowledge_point_ids,
    difficulty_coefficient,
    question_no,
    year=2026,
    score=5,
    mapping_status="confirmed",
):
    return ExamQuestion(
        question_id=question_id,
        exam_type="math1",
        year=year,
        question_no=question_no,
        section="选择题",
        score=score,
        difficulty_coefficient=difficulty_coefficient,
        question_text=f"题目 {question_id}",
        answer="A",
        explanation="解析",
        knowledge_point_ids=tuple(knowledge_point_ids),
        source_reference="test",
        mapping_status=mapping_status,
        data_version="v1",
    )


class MathPersonalizationTests(unittest.TestCase):
    def test_diagnostic_question_pool_has_a_filtering_index(self):
        connection = sqlite3.connect(":memory:")

        ensure_schema(connection)

        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list('math_exam_questions')")
        }
        self.assertIn("ix_math_exam_diagnostic_pool", indexes)

    def test_legacy_user_profile_math_type_selects_the_matching_math_version(self):
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE user_profiles (user_id INTEGER PRIMARY KEY, math_exam_type TEXT)"
        )

        for value, expected in (("数一", "math1"), ("数学二", "math2"), ("math3", "math3")):
            connection.execute(
                "INSERT OR REPLACE INTO user_profiles (user_id, math_exam_type) VALUES (?, ?)",
                (1, value),
            )
            self.assertEqual(get_legacy_math_exam_type(connection, 1), expected)

    def test_missing_legacy_user_profile_math_type_returns_no_default(self):
        connection = sqlite3.connect(":memory:")
        self.assertIsNone(get_legacy_math_exam_type(connection, 1))

    def test_legacy_math_profile_aliases_cover_all_three_versions(self):
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE user_profiles (user_id INTEGER PRIMARY KEY, math_exam_type TEXT)"
        )

        for value, expected in (
            ("数学一专属", "math1"),
            ("数二专属", "math2"),
            ("数学3", "math3"),
            ("math_2", "math2"),
        ):
            connection.execute(
                "INSERT OR REPLACE INTO user_profiles (user_id, math_exam_type) VALUES (?, ?)",
                (1, value),
            )
            self.assertEqual(resolve_math_exam_type(connection, 1), expected)

    def test_new_math_profile_takes_precedence_over_legacy_portrait(self):
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE user_profiles (user_id INTEGER PRIMARY KEY, math_exam_type TEXT)"
        )
        connection.execute(
            "INSERT INTO user_profiles (user_id, math_exam_type) VALUES (?, ?)",
            (1, "数一"),
        )

        profile = type("Profile", (), {"exam_type": EXAM_TYPES["数学三"]})()

        self.assertEqual(resolve_math_exam_type(connection, 1, profile), "math3")

    def test_difficulty_coefficient_larger_means_easier_and_profile_is_validated(self):
        self.assertEqual(classify_difficulty(0.8), "基础")
        self.assertEqual(classify_difficulty(0.55), "标准")
        self.assertEqual(classify_difficulty(0.2), "提高")

        with self.assertRaises(ValueError):
            StudentProfile(
                user_id="u1",
                subject_code="math",
                exam_type="math1",
                target_score=151,
                current_score=60,
                score_source="self_reported",
            )

    def test_exam_import_rejects_bad_rows_deduplicates_and_hides_unconfirmed_questions(self):
        connection = sqlite3.connect(":memory:")
        ensure_schema(connection)
        rows = [
            make_question("q-confirmed", ("limit",), 0.8, 1),
            make_question("q-pending", (), 0.55, 2, mapping_status="pending"),
        ]

        self.assertEqual(
            import_exam_questions(connection, rows, data_version="v1"),
            {"imported": 2, "skipped": 0},
        )
        self.assertEqual(
            import_exam_questions(connection, [rows[0]], data_version="v1"),
            {"imported": 0, "skipped": 1},
        )
        self.assertEqual(len(list_eligible_exam_questions(connection, "math1")), 1)
        self.assertEqual(
            connection.execute(
                "SELECT question_text FROM math_exam_questions WHERE question_id=?",
                ("q-confirmed",),
            ).fetchone()[0],
            "题目 q-confirmed",
        )

        with self.assertRaisesRegex(ValueError, "difficulty_coefficient"):
            import_exam_questions(
                connection,
                [make_question("q-invalid", ("limit",), 1.2, 3)],
                data_version="v1",
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "questions.json"
            json_path.write_text(
                '{"questions": [{"exam_type": "math1", "year": 2026, "question_no": "4", '
                '"section": "选择题", "score": 4, "difficulty_coefficient": 0.7, '
                '"question_text": "JSON题", "answer": "B", "explanation": "解析", '
                '"knowledge_point_ids": ["matrix"], "mapping_status": "confirmed"}]}',
                encoding="utf-8",
            )
            self.assertEqual(load_exam_question_rows(json_path)[0]["question_text"], "JSON题")

            csv_path = Path(temp_dir) / "questions.csv"
            csv_path.write_text(
                "exam_type,year,question_no,section,score,difficulty_coefficient,"
                "question_text,answer,explanation,knowledge_point_ids,mapping_status\n"
                "math1,2026,5,选择题,4,0.7,CSV题,B,解析,probability,confirmed\n",
                encoding="utf-8",
            )
            self.assertEqual(load_exam_question_rows(csv_path)[0]["question_text"], "CSV题")

        version_two = make_question("q-confirmed-v2", ("limit",), 0.8, 1)
        version_two = version_two.__class__(
            **{**version_two.__dict__, "question_id": "q-confirmed", "data_version": "v2", "question_text": "新版本题目"}
        )
        self.assertEqual(import_exam_questions(connection, [version_two], data_version="v2")["imported"], 1)
        self.assertEqual(len(list_eligible_exam_questions(connection, "math1", "v2")), 1)

        pending = make_question("pending-map", (), 0.7, 6, mapping_status="pending")
        import_exam_questions(connection, [pending], data_version="v1")
        self.assertTrue(confirm_question_mapping(connection, "pending-map", "v1", ("probability",)))
        self.assertEqual(len(list_eligible_exam_questions(connection, "math1", "v1")), 2)

    def test_ai_suggested_mapping_keeps_question_out_of_true_question_weights(self):
        connection = sqlite3.connect(":memory:")
        ensure_schema(connection)
        question = make_question("suggested-map", (), 0.7, 7, mapping_status="pending")
        import_exam_questions(connection, [question], data_version="v1")

        self.assertTrue(suggest_question_mapping(connection, "suggested-map", "v1", ("064-多元函数微分学.md",)))

        self.assertEqual(list_eligible_exam_questions(connection, "math1", "v1"), [])
        self.assertEqual(list_diagnostic_questions(connection, "math1", "v1")[0].knowledge_point_ids, ("064-多元函数微分学.md",))

    def test_repairs_question_mark_legacy_mapping_ids_from_the_knowledge_catalog(self):
        connection = sqlite3.connect(":memory:")
        ensure_schema(connection)
        legacy = make_question("legacy", ("064-???????.md",), 0.8, 8, mapping_status="confirmed")
        import_exam_questions(connection, [legacy], data_version="v1")
        save_evidence(connection, MasteryEvidence("u1", "064-???????.md", "legacy", False, 0.8))

        repaired = repair_legacy_question_mapping_ids(
            connection,
            ("064-多元函数微分学.md", "067-无穷级数.md"),
        )

        self.assertEqual(repaired, 1)
        self.assertEqual(
            list_eligible_exam_questions(connection, "math1")[0].knowledge_point_ids,
            ("064-多元函数微分学.md",),
        )
        self.assertIn("064-多元函数微分学.md", get_mastery_snapshots(connection, "u1"))

    def test_profile_and_evidence_storage_is_isolated_by_user(self):
        connection = sqlite3.connect(":memory:")
        ensure_schema(connection)
        user_one = StudentProfile("u1", "math", "math1", 100, 50, "diagnostic")
        user_two = StudentProfile("u2", "math", "math1", 100, 50, "diagnostic")
        save_profile(connection, user_one)
        save_profile(connection, user_two)
        save_evidence(
            connection,
            MasteryEvidence("u1", "limit", "diagnosis-1", False, 0.8, "概念不清"),
        )

        self.assertEqual(get_mastery_snapshots(connection, "u2"), {})
        self.assertEqual(get_mastery_snapshots(connection, "u1")["limit"].times_wrong, 1)

    def test_profile_persists_exam_goal_record_fields_without_affecting_math_scores(self):
        connection = sqlite3.connect(":memory:")
        ensure_schema(connection)
        profile = StudentProfile(
            "u1", "math", "math1", 110, 55, "mock",
            target_school="北京大学",
            target_major="计算机科学与技术",
            undergraduate_major="软件工程",
            is_cross_exam=True,
            current_stage="强化阶段",
        )

        save_profile(connection, profile)
        stored = get_profile(connection, "u1")

        self.assertEqual(stored.target_score, 110)
        self.assertEqual(stored.target_school, "北京大学")
        self.assertEqual(stored.target_major, "计算机科学与技术")
        self.assertTrue(stored.is_cross_exam)
        self.assertEqual(stored.current_stage, "强化阶段")

    def test_diagnosis_plan_covers_knowledge_points_and_answer_updates_mastery(self):
        plan = build_diagnosis_plan(("limit", "matrix", "probability"), question_count=20)
        self.assertEqual(len(plan), 20)
        self.assertEqual(
            {item.knowledge_point_id for item in plan},
            {"limit", "matrix", "probability"},
        )
        self.assertEqual({item.difficulty_tier for item in plan}, {"基础", "标准", "提高"})

        now = datetime.now(timezone.utc)
        wrong = record_diagnosis_answer(
            user_id="u-weak",
            question_id="diagnosis-1",
            knowledge_point_ids=("limit",),
            is_correct=False,
            difficulty_coefficient=0.8,
            error_type="概念不清",
            answered_at=now,
        )
        correct = record_diagnosis_answer(
            user_id="u-strong",
            question_id="diagnosis-2",
            knowledge_point_ids=("limit",),
            is_correct=True,
            difficulty_coefficient=0.3,
            error_type="",
            answered_at=now,
        )
        weak_snapshot = calculate_mastery(wrong)["limit"]
        strong_snapshot = calculate_mastery(correct)["limit"]
        self.assertLess(weak_snapshot.mastery, strong_snapshot.mastery)
        self.assertLess(weak_snapshot.forgetting_risk, 0.5)

    def test_requires_twenty_distinct_diagnosis_answers_before_showing_requirements(self):
        incomplete = [MasteryEvidence("u1", "limit", f"q-{index}", False, 0.8) for index in range(19)]
        complete = incomplete + [MasteryEvidence("u1", "matrix", "q-19", True, 0.8)]

        self.assertFalse(has_completed_diagnosis(incomplete))
        self.assertTrue(has_completed_diagnosis(complete))

    def test_stage_reassessment_only_counts_answers_from_its_own_batch(self):
        first = [MasteryEvidence("u1", "limit", f"first-{index}", True, 0.8, source="diagnosis:first") for index in range(20)]
        second = [MasteryEvidence("u1", "matrix", f"second-{index}", True, 0.8, source="diagnosis:second") for index in range(19)]

        self.assertTrue(has_completed_diagnosis(first + second, session_id="first"))
        self.assertFalse(has_completed_diagnosis(first + second, session_id="second"))

    def test_evidence_storage_keeps_math_versions_isolated(self):
        connection = sqlite3.connect(":memory:")
        ensure_schema(connection)
        save_profile(connection, StudentProfile("u1", "math", "math1", 100, 50, "diagnostic"))

        save_evidence(
            connection,
            MasteryEvidence("u1", "limit", "math1-q", False, 0.8, exam_type="math1"),
        )
        save_evidence(
            connection,
            MasteryEvidence("u1", "matrix", "math2-q", True, 0.8, exam_type="math2"),
        )

        math1 = get_mastery_snapshots(connection, "u1", "math1")
        math2 = get_mastery_snapshots(connection, "u1", "math2")
        self.assertEqual(set(math1), {"limit"})
        self.assertEqual(set(math2), {"matrix"})

    def test_multi_knowledge_question_does_not_duplicate_one_evidence_item(self):
        from personalized_learning.math.diagnosis_report import build_diagnosis_report

        profile = StudentProfile("u1", "math", "math1", 100, 50, "diagnostic")
        question = make_question("multi", ("limit", "matrix"), 0.8, 1)
        evidence = (MasteryEvidence("u1", "limit", "multi", False, 0.8),)

        report = build_diagnosis_report(profile, (question,), evidence)

        self.assertEqual([item.knowledge_point_id for item in report], ["limit"])
        self.assertEqual(report[0].question_count, 1)

    def test_equivalent_numeric_answers_are_accepted_but_unknown_open_answers_need_review(self):
        numeric = make_question("numeric", ("limit",), 0.8, 1)
        numeric = numeric.__class__(**{**numeric.__dict__, "answer": "1/2"})
        open_question = numeric.__class__(**{**numeric.__dict__, "question_id": "open", "answer": "x^2 + 1"})

        self.assertTrue(is_math_answer_correct(numeric, "0.5"))
        self.assertFalse(is_math_answer_correct(numeric, "0.6"))
        self.assertIsNone(is_math_answer_correct(open_question, "x²+1"))

    def test_same_scores_with_different_knowledge_profiles_produce_different_requirements(self):
        profile = StudentProfile("u1", "math", "math1", 100, 50, "mock")
        questions = [
            make_question("limit-basic", ("limit",), 0.8, 1),
            make_question("limit-standard", ("limit",), 0.55, 2),
            make_question("limit-stretch", ("limit",), 0.2, 3, score=10),
            make_question("matrix-basic", ("matrix",), 0.8, 4),
            make_question("matrix-standard", ("matrix",), 0.55, 5),
            make_question("matrix-stretch", ("matrix",), 0.2, 6, score=10),
        ]
        weak_limit = calculate_mastery(
            [MasteryEvidence("u1", "limit", "d1", False, 0.8, "概念不清")]
        )
        strong_matrix = calculate_mastery(
            [MasteryEvidence("u1", "matrix", "d2", True, 0.3, "")]
        )
        first = build_requirements(profile, {**weak_limit, **strong_matrix}, questions)

        strong_limit = calculate_mastery(
            [MasteryEvidence("u1", "limit", "d3", True, 0.8, "")]
        )
        weak_matrix = calculate_mastery(
            [MasteryEvidence("u1", "matrix", "d4", False, 0.3, "计算错误")]
        )
        second = build_requirements(profile, {**strong_limit, **weak_matrix}, questions)

        self.assertGreater(
            first.priority_by_knowledge["limit"],
            second.priority_by_knowledge["limit"],
        )

    def test_build_requirements_keeps_knowledge_points_without_confirmed_exam_mapping(self):
        profile = StudentProfile("u1", "math", "math1", 100, 50, "mock")
        questions = [make_question("limit-basic", ("limit",), 0.8, 1)]

        result = build_requirements(
            profile,
            {},
            questions,
            knowledge_point_ids=("limit", "matrix", "probability"),
        )

        all_ids = {
            item.knowledge_point_id
            for group in (result.must, result.should, result.stretch)
            for item in group
        }
        self.assertEqual(all_ids, {"limit", "matrix", "probability"})
        matrix = next(item for group in (result.must, result.should, result.stretch) for item in group if item.knowledge_point_id == "matrix")
        self.assertEqual(matrix.related_question_ids, ())
        self.assertEqual(matrix.expected_contribution, 0.0)
        self.assertIn("待补", matrix.reason)

    def test_higher_target_increases_stretch_weight_and_over_target_enters_consolidation_mode(self):
        low = StudentProfile("low", "math", "math1", 60, 40, "self_reported")
        high = StudentProfile("high", "math", "math1", 125, 40, "self_reported")
        above_target = StudentProfile("above", "math", "math1", 80, 95, "diagnostic")
        questions = [
            make_question("basic", ("limit",), 0.8, 1),
            make_question("standard", ("limit",), 0.55, 2),
            make_question("stretch", ("limit",), 0.2, 3, score=10),
        ]
        mastery = calculate_mastery([])

        low_result = build_requirements(low, mastery, questions)
        high_result = build_requirements(high, mastery, questions)
        above_result = build_requirements(above_target, mastery, questions)

        self.assertTrue(high_result.stretch)
        self.assertGreaterEqual(len(high_result.stretch), len(low_result.stretch))
        self.assertEqual(above_result.mode, "巩固与冲刺")

    def test_diagnostic_requirements_work_before_real_exam_mapping_is_imported(self):
        profile = StudentProfile("u1", "math", "math1", 100, 50, "diagnostic")
        weak = calculate_mastery(
            [MasteryEvidence("u1", "limit", "d1", False, 0.8, "概念不清")]
        )
        result = build_diagnostic_requirements(profile, weak, ("limit", "matrix"))

        self.assertTrue(result.must)
        self.assertEqual(result.must[0].knowledge_point_id, "limit")
        self.assertIn("诊断", result.must[0].reason)

    def test_selector_uses_weakness_real_exam_weight_and_recent_filter(self):
        profile = StudentProfile("u1", "math", "math1", 100, 50, "diagnostic")
        now = datetime.now(timezone.utc)
        weak = calculate_mastery(
            [MasteryEvidence("u1", "limit", "wrong-1", False, 0.8, "概念不清", now - timedelta(days=2))]
        )
        strong = calculate_mastery(
            [MasteryEvidence("u1", "matrix", "right-1", True, 0.3, "", now - timedelta(days=2))]
        )
        questions = [
            make_question("weak-basic", ("limit",), 0.8, 1, year=2026, score=5),
            make_question("strong-stretch", ("matrix",), 0.2, 2, year=2026, score=10),
            make_question("weak-recent", ("limit",), 0.8, 3, year=2025, score=5),
        ]

        selected = select_next_question(
            profile,
            {**weak, **strong},
            questions,
            recent_question_ids=("weak-recent",),
        )
        self.assertEqual(selected.question_id, "weak-basic")
        self.assertIsNone(
            select_next_question(
                profile,
                {**weak, **strong},
                questions,
                recent_question_ids=tuple(question.question_id for question in questions),
            )
        )

    def test_generator_and_training_material_are_injected_without_llm_side_effects(self):
        plan = build_diagnosis_plan(("limit",), question_count=2)
        calls = []

        def generator(request):
            calls.append(request)
            return {"question": request.knowledge_point_id, "tier": request.difficulty_tier}

        generated = generate_diagnosis_questions(generator, plan)
        self.assertEqual(len(generated), 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].purpose, "diagnosis")

        snapshot = calculate_mastery(
            [MasteryEvidence("u1", "limit", "q1", False, 0.8, "概念不清")]
        )["limit"]
        requirement = build_requirements(
            StudentProfile("u1", "math", "math1", 100, 50, "diagnostic"),
            {"limit": snapshot},
            [make_question("basic", ("limit",), 0.8, 1)],
        ).must[0]
        material_request = build_training_material_request(requirement)
        self.assertEqual(material_request.knowledge_point_id, "limit")
        self.assertEqual(material_request.evidence_summary["last_error_type"], "概念不清")

    def test_existing_math_knowledge_generator_can_be_adapted_without_importing_app(self):
        calls = []

        def existing_generator(knowledge_points):
            calls.append(knowledge_points)
            return "Q: 诊断题"

        adapter = adapt_existing_review_generator(existing_generator)
        plan = build_diagnosis_plan(("limit",), question_count=1)
        self.assertEqual(generate_diagnosis_questions(adapter, plan), ["Q: 诊断题"])
        self.assertEqual(calls[0][0]["knowledge_id"], "limit")
        self.assertEqual(calls[0][0]["difficulty_tier"], "基础")


if __name__ == "__main__":
    unittest.main()
