import sqlite3
import unittest

from repositories.knowledge_repo import ensure_knowledge_schema, save_confirmed_knowledge_points
from repositories.professional_learning_repo import (
    ensure_memory_rows,
    list_saved_questions,
    list_memory_states,
    list_recent_study_records,
    mark_saved_question_practiced,
    record_study_result,
    save_generated_question,
    set_review_due_now,
)


class ProfessionalLearningRepoTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        ensure_knowledge_schema(self.conn)
        save_confirmed_knowledge_points(
            self.conn,
            user_id=7,
            points=[
                {
                    "knowledge_name": "页式虚拟存储器",
                    "core_definition": "使用页表完成虚拟地址到物理地址的转换。",
                    "source_text": "教材原文",
                    "mastery_state": "待复习",
                }
            ],
            material_meta={"subject": "408综合"},
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM user_knowledge").fetchone()
        columns = [item[0] for item in self.conn.execute("SELECT * FROM user_knowledge").description]
        self.point = dict(zip(columns, row))

    def tearDown(self):
        self.conn.close()

    def test_records_results_and_updates_review_schedule(self):
        ensure_memory_rows(self.conn, 7, "408综合", [self.point])
        initial = list_memory_states(self.conn, 7, "408综合")[0]
        self.assertAlmostEqual(initial["mastery_score"], 0.0)

        saved = record_study_result(
            self.conn,
            user_id=7,
            subject="408综合",
            knowledge_id=self.point["id"],
            study_mode="quiz",
            question="页表有什么作用？",
            user_answer="完成地址转换。",
            feedback="核心结论正确。",
            score=84,
            rating="good",
        )
        self.conn.commit()

        self.assertGreater(saved["mastery_score"], 0.0)
        self.assertGreaterEqual(saved["interval_days"], 2)
        state = list_memory_states(self.conn, 7, "408综合")[0]
        self.assertEqual(state["review_count"], 1)
        self.assertEqual(state["correct_count"], 1)
        records = list_recent_study_records(self.conn, 7, "408综合")
        self.assertEqual(records[0]["score"], 84)
        self.assertEqual(records[0]["knowledge_name"], "页式虚拟存储器")

    def test_again_lowers_mastery_and_due_now_can_be_requested(self):
        ensure_memory_rows(self.conn, 7, "408综合", [self.point])
        first = record_study_result(
            self.conn,
            user_id=7,
            subject="408综合",
            knowledge_id=self.point["id"],
            study_mode="review",
            question="回忆知识点",
            user_answer="记不清",
            feedback="近期再复习。",
            score=30,
            rating="again",
        )
        set_review_due_now(self.conn, 7, "408综合", self.point["id"])
        self.conn.commit()

        self.assertGreaterEqual(first["mastery_score"], 0.05)
        state = list_memory_states(self.conn, 7, "408综合")[0]
        self.assertEqual(state["lapse_count"], 1)
        self.assertIsNotNone(state["next_review"])

    def test_unreviewed_legacy_initial_mastery_is_reset_to_zero(self):
        ensure_memory_rows(self.conn, 7, "408综合", [self.point])
        self.conn.execute(
            """UPDATE professional_memory
               SET mastery_score=0.30, review_count=0, correct_count=0, lapse_count=0"""
        )
        self.conn.commit()

        ensure_memory_rows(self.conn, 7, "408综合", [self.point])
        state = list_memory_states(self.conn, 7, "408综合")[0]

        self.assertAlmostEqual(state["mastery_score"], 0.0)

    def test_saved_questions_can_be_listed_and_marked_practiced(self):
        saved = save_generated_question(
            self.conn,
            user_id=7,
            subject="408综合",
            knowledge_id=self.point["id"],
            question="某系统采用页式虚拟存储器，给定虚拟页号后如何完成地址转换？",
            reference_answer="通过页表查询物理块号，再与页内地址拼接。",
            grading_points=["页表", "物理块号", "页内地址"],
            source_mode="quiz",
        )
        self.conn.commit()

        questions = list_saved_questions(self.conn, 7, "408综合")
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["id"], saved["id"])
        self.assertEqual(questions[0]["knowledge_name"], "页式虚拟存储器")
        self.assertEqual(questions[0]["practice_count"], 0)

        mark_saved_question_practiced(self.conn, saved["id"])
        self.conn.commit()
        practiced = list_saved_questions(self.conn, 7, "408综合")[0]
        self.assertEqual(practiced["practice_count"], 1)
        self.assertIsNotNone(practiced["last_practiced"])

    def test_saved_questions_keep_multiple_records_even_for_same_prompt(self):
        for _ in range(2):
            save_generated_question(
                self.conn,
                user_id=7,
                subject="408综合",
                knowledge_id=self.point["id"],
                question="同一道题也应该作为两次保存记录保留下来。",
                reference_answer="参考答案。",
                grading_points=["得分点"],
                source_mode="quiz",
            )
        self.conn.commit()

        questions = list_saved_questions(self.conn, 7, "408综合")

        self.assertEqual(len(questions), 2)
        self.assertNotEqual(questions[0]["id"], questions[1]["id"])


if __name__ == "__main__":
    unittest.main()
