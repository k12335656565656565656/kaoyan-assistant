import unittest

from personalized_learning.math.diagnosis_report import (
    build_diagnosis_report,
    build_diagnosis_summary_prompt,
)
from personalized_learning.models import ExamQuestion, MasteryEvidence, StudentProfile


def question(question_id, knowledge_id, coefficient, mapping_status="confirmed"):
    return ExamQuestion(
        question_id=question_id,
        exam_type="math1",
        year=2024,
        question_no=question_id,
        section="选择题" if mapping_status == "confirmed" else "AI 真题变式",
        score=5,
        difficulty_coefficient=coefficient,
        question_text="题目",
        answer="A",
        explanation="解析",
        knowledge_point_ids=(knowledge_id,),
        mapping_status=mapping_status,
    )


class DiagnosisReportTests(unittest.TestCase):
    def test_wrong_hard_true_question_has_a_higher_weakness_weight(self):
        profile = StudentProfile("u1", "math", "math1", 110, 60, "diagnostic")
        questions = (
            question("real-hard", "limit", 0.35),
            question("variant-easy", "matrix", 0.8, "ai_suggested"),
        )
        evidence = (
            MasteryEvidence("u1", "limit", "real-hard", False, 0.35, "诊断答错；反馈: 知识点遗漏"),
            MasteryEvidence("u1", "matrix", "variant-easy", False, 0.8, "诊断答错；反馈: 偏简单"),
        )

        report = build_diagnosis_report(profile, questions, evidence)

        self.assertEqual(report[0].knowledge_point_id, "limit")
        self.assertGreater(report[0].weakness_score, report[1].weakness_score)
        self.assertIn("知识点遗漏", report[0].feedback)

    def test_summary_prompt_is_grounded_in_weighted_evidence(self):
        profile = StudentProfile("u1", "math", "math1", 110, 60, "diagnostic")
        report = build_diagnosis_report(
            profile,
            (question("real", "limit", 0.8),),
            (MasteryEvidence("u1", "limit", "real", False, 0.8, "诊断答错；反馈: 偏难"),),
        )

        prompt = build_diagnosis_summary_prompt(profile, report)

        self.assertIn("不得编造", prompt)
        self.assertIn("limit", prompt)
        self.assertIn("加权薄弱分", prompt)

    def test_includes_evidence_from_a_stage_reassessment_session(self):
        profile = StudentProfile("u1", "math", "math1", 110, 60, "diagnostic")
        report = build_diagnosis_report(
            profile,
            (question("stage-question", "limit", 0.8),),
            (MasteryEvidence("u1", "limit", "stage-question", False, 0.8, source="diagnosis:stage-2"),),
        )

        self.assertEqual(report[0].knowledge_point_id, "limit")
        self.assertEqual(report[0].wrong_count, 1)
