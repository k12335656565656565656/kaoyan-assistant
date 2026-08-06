import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from personalized_learning.repository import (
    ensure_schema,
    list_diagnostic_questions,
    seed_question_bank_from_file,
)


class QuestionBankSeedTests(unittest.TestCase):
    def test_seeds_json_questions_once_and_preserves_data_versions(self):
        payload = {
            "format": "kaoyan-assistant.math_exam_question_bank.v1",
            "subject_code": "math",
            "exam_type": "math1",
            "question_count": 2,
            "questions": [
                {
                    "question_id": "math1:2025:1:2025-screenshot-v1",
                    "exam_type": "math1",
                    "year": 2025,
                    "question_no": "1",
                    "section": "选择题",
                    "score": 4,
                    "difficulty_coefficient": 0.8,
                    "question_text": "真题题目",
                    "answer": "A",
                    "explanation": "真题解析",
                    "knowledge_point_ids": ["limit"],
                    "source_reference": "true_exam:2025/math1/1",
                    "mapping_status": "ai_suggested",
                    "data_version": "2025-screenshot-v1",
                },
                {
                    "question_id": "ai_variant:math1:2026:1:v1",
                    "exam_type": "math1",
                    "year": 2026,
                    "question_no": "1",
                    "section": "AI 真题变式",
                    "score": 4,
                    "difficulty_coefficient": 0.7,
                    "question_text": "变式题目",
                    "answer": "B",
                    "explanation": "变式解析",
                    "knowledge_point_ids": ["limit"],
                    "source_reference": "ai_variant:math1:2026:1:v1",
                    "mapping_status": "ai_suggested",
                    "data_version": "generated-v1",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            bank_path = Path(temp_dir) / "question-bank.json"
            bank_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            connection = sqlite3.connect(":memory:")
            ensure_schema(connection)

            first = seed_question_bank_from_file(connection, bank_path)
            second = seed_question_bank_from_file(connection, bank_path)

            self.assertEqual(first["imported"], 2)
            self.assertEqual(second["imported"], 0)
            self.assertEqual(second["skipped"], 2)
            questions = list_diagnostic_questions(connection, "math1")
            self.assertEqual(len(questions), 2)
            self.assertEqual(
                {question.data_version for question in questions},
                {"2025-screenshot-v1", "generated-v1"},
            )
            connection.close()


if __name__ == "__main__":
    unittest.main()
