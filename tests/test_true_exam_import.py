import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from personalized_learning.math.true_exam_import import (
    build_extraction_prompt,
    discover_screenshot_tasks,
    parse_extraction_response,
    run_staged_import,
    save_extraction_responses,
)
from personalized_learning.math.knowledge_mapping import suggest_knowledge_point_ids
from personalized_learning.repository import (
    confirm_question_mapping,
    ensure_schema,
    import_exam_questions,
    list_diagnostic_questions,
    refresh_provisional_question_mappings,
)


class TrueExamImportTests(unittest.TestCase):
    def test_discovers_sorted_screenshots_as_year_and_exam_scoped_tasks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "2026" / "screenshots" / "math1"
            folder.mkdir(parents=True)
            (folder / "pdf_page_0011.png").write_bytes(b"png")
            (folder / "pdf_page_0009.png").write_bytes(b"png")

            tasks = discover_screenshot_tasks(Path(temp_dir), 2026, "math1")

        self.assertEqual([task.page_name for task in tasks], ["pdf_page_0009.png", "pdf_page_0011.png"])
        self.assertTrue(all(task.exam_type == "math1" and task.year == 2026 for task in tasks))

    def test_parses_strict_json_to_traceable_provisional_question_rows(self):
        raw = json.dumps({"questions": [{
            "question_no": "1",
            "section": "选择题",
            "score": 4,
            "difficulty_coefficient": 0.8,
            "question_text": "设 $f(x)=x$，则 $f(1)$ 为（ ）\nA) 0\nB) 1\nC) 2\nD) 3",
            "answer": "B",
            "explanation": "代入 $x=1$。",
            "knowledge_point_ids": ["function-basic"],
        }]}, ensure_ascii=False)

        rows, errors = parse_extraction_response(raw, year=2026, exam_type="math1", page_name="pdf_page_0910.png")

        self.assertEqual(errors, ())
        self.assertEqual(rows[0]["mapping_status"], "ai_suggested")
        self.assertEqual(rows[0]["source_reference"], "2026/math1/pdf_page_0910.png")
        self.assertEqual(rows[0]["knowledge_point_ids"], ["function-basic"])

    def test_does_not_guess_knowledge_mapping_from_the_local_catalog(self):
        raw = json.dumps({"questions": [{
            "question_no": "1",
            "section": "选择题",
            "score": 4,
            "difficulty_coefficient": 0.8,
            "question_text": "设矩阵 A 的特征值为 1, 2, 3，求对应的特征向量。",
            "answer": "A",
            "explanation": "本题考查特征值与特征向量。",
            "knowledge_point_ids": [],
        }]}, ensure_ascii=False)

        rows, errors = parse_extraction_response(
            raw,
            year=2025,
            exam_type="math1",
            page_name="pdf_page_0001.png",
            knowledge_catalog=(
                {"id": "031-特征值与特征向量.md", "text": "矩阵的特征值与特征向量"},
                {"id": "012-定积分的定义与性质.md", "text": "定积分的定义与性质"},
            ),
        )

        self.assertEqual(errors, ())
        self.assertEqual(rows[0]["knowledge_point_ids"], [])
        self.assertEqual(rows[0]["mapping_status"], "pending")

    def test_rejects_model_tags_outside_the_catalog_and_stages_question_for_review(self):
        raw = json.dumps({"questions": [{
            "question_no": "1",
            "section": "选择题",
            "score": 4,
            "difficulty_coefficient": 0.8,
            "question_text": "题干",
            "answer": "A",
            "explanation": "解析",
            "knowledge_point_ids": ["not-in-catalog"],
        }]}, ensure_ascii=False)

        rows, errors = parse_extraction_response(
            raw,
            year=2026,
            exam_type="math1",
            page_name="page.png",
            knowledge_catalog=({"id": "031-特征值与特征向量.md", "text": "特征值"},),
        )

        self.assertEqual(errors, ())
        self.assertEqual(rows[0]["knowledge_point_ids"], [])
        self.assertEqual(rows[0]["mapping_status"], "pending")

    def test_knowledge_mapping_returns_empty_when_the_question_has_no_catalog_evidence(self):
        self.assertEqual(
            suggest_knowledge_point_ids(
                "这是一道无法判断考点的题。",
                "暂无可用解析。",
                ({"id": "031-特征值与特征向量.md", "text": "矩阵特征值"},),
            ),
            (),
        )

    def test_knowledge_mapping_uses_math_aliases_when_the_question_uses_a_different_phrase(self):
        self.assertEqual(
            suggest_knowledge_point_ids(
                "设 z=z(x,y)，求 z 对 x 和 y 的偏导数。",
                "利用全微分关系整理隐函数。",
                ({"id": "064-多元函数微分学.md", "text": "偏导数 全微分 隐函数"},),
            ),
            ("064-多元函数微分学.md",),
        )

    def test_rejects_incomplete_or_invalid_model_records_without_losing_valid_rows(self):
        raw = json.dumps({"questions": [
            {"question_no": "1", "section": "选择题", "score": 4, "difficulty_coefficient": 0.8, "question_text": "有效题", "answer": "A", "explanation": "解析"},
            {"question_no": "2", "question_text": "缺少答案"},
        ]}, ensure_ascii=False)

        rows, errors = parse_extraction_response(raw, year=2026, exam_type="math1", page_name="page.png")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["question_no"], "1")
        self.assertEqual(len(errors), 1)
        self.assertIn("question 2", errors[0])

    def test_prompt_requires_json_and_forbids_model_reasoning(self):
        prompt = build_extraction_prompt(
            "math1",
            2026,
            "pdf_page_0910.png",
            knowledge_catalog=({"id": "031-特征值与特征向量.md", "text": "特征值和特征向量"},),
        )

        self.assertIn("JSON", prompt)
        self.assertIn("不得输出思考过程", prompt)
        self.assertIn("pdf_page_0910.png", prompt)
        self.assertIn("双反斜杠", prompt)
        self.assertIn("知识点标签必须由 Mimo 模型根据图片", prompt)
        self.assertIn("031-特征值与特征向量.md", prompt)
        self.assertIn("特征值和特征向量", prompt)

    def test_accepts_a_json_object_with_only_an_extra_closing_brace_from_mimo(self):
        raw = '{"questions": [{"question_no": "1", "section": "选择题", "score": 4, "difficulty_coefficient": 0.8, "question_text": "题干", "answer": "A", "explanation": "解析"}]}}'

        rows, errors = parse_extraction_response(raw, year=2026, exam_type="math1", page_name="page.png")

        self.assertEqual(errors, ())
        self.assertEqual(rows[0]["question_no"], "1")

    def test_accepts_question_without_explanation_when_the_answer_book_has_no_solution(self):
        raw = '{"questions": [{"question_no": "1", "section": "选择题", "score": 4, "difficulty_coefficient": 0.8, "question_text": "题干", "answer": "A"}]}'

        rows, errors = parse_extraction_response(raw, year=2026, exam_type="math1", page_name="page.png")

        self.assertEqual(errors, ())
        self.assertEqual(rows[0]["explanation"], "")

    def test_imports_saved_model_responses_as_provisional_rows_and_writes_staging_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "data"
            page_dir = root / "2026" / "screenshots" / "math1"
            response_dir = root / "2026" / "responses" / "math1"
            page_dir.mkdir(parents=True)
            response_dir.mkdir(parents=True)
            (page_dir / "pdf_page_0910.png").write_bytes(b"png")
            (response_dir / "pdf_page_0910.json").write_text(json.dumps({"questions": [{
                "question_no": "1", "section": "选择题", "score": 4, "difficulty_coefficient": 0.8,
                "question_text": "题干", "answer": "A", "explanation": "解析",
                "knowledge_point_ids": ["031-特征值与特征向量.md"],
            }]}, ensure_ascii=False), encoding="utf-8")
            connection = sqlite3.connect(":memory:")
            ensure_schema(connection)

            result = run_staged_import(root, 2026, "math1", response_dir, root / "2026" / "staging" / "math1.json", connection)

            self.assertEqual(result["imported"], 1)
            self.assertTrue((root / "2026" / "staging" / "math1.json").exists())
            self.assertEqual(list_diagnostic_questions(connection, "math1")[0].mapping_status, "ai_suggested")

    def test_reimports_new_provisional_tags_without_overwriting_confirmed_mappings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "data"
            page_dir = root / "2025" / "screenshots" / "math1"
            response_dir = root / "2025" / "responses" / "math1"
            page_dir.mkdir(parents=True)
            response_dir.mkdir(parents=True)
            (page_dir / "pdf_page_0001.png").write_bytes(b"png")
            response_path = response_dir / "pdf_page_0001.json"
            response_path.write_text(json.dumps({"questions": [{
                "question_no": "1", "section": "选择题", "score": 4, "difficulty_coefficient": 0.8,
                "question_text": "未标记题", "answer": "A", "explanation": "解析", "knowledge_point_ids": [],
            }]}, ensure_ascii=False), encoding="utf-8")
            connection = sqlite3.connect(":memory:")
            ensure_schema(connection)

            catalog = ({"id": "031-特征值与特征向量.md", "text": "无关目录"},)
            run_staged_import(root, 2025, "math1", response_dir, root / "staging.json", connection, catalog)

            pending_row = connection.execute(
                "SELECT mapping_status, knowledge_point_ids FROM math_exam_questions WHERE question_id=?",
                ("math1:2025:1:2025-screenshot-v1",),
            ).fetchone()
            self.assertEqual(pending_row[0], "pending")
            self.assertEqual(json.loads(pending_row[1]), [])
            self.assertTrue(
                confirm_question_mapping(
                    connection,
                    "math1:2025:1:2025-screenshot-v1",
                    "2025-screenshot-v1",
                    ("031-特征值与特征向量.md",),
                )
            )
            question = list_diagnostic_questions(connection, "math1")[0]
            self.assertEqual(question.knowledge_point_ids, ("031-特征值与特征向量.md",))

            response_path.write_text(json.dumps({"questions": [{
                "question_no": "1", "section": "选择题", "score": 4, "difficulty_coefficient": 0.8,
                "question_text": "未标记题", "answer": "A", "explanation": "解析", "knowledge_point_ids": ["032-特征值的性质与计算.md"],
            }]}, ensure_ascii=False), encoding="utf-8")
            run_staged_import(root, 2025, "math1", response_dir, root / "staging.json", connection, catalog)

            self.assertEqual(
                list_diagnostic_questions(connection, "math1")[0].knowledge_point_ids,
                ("031-特征值与特征向量.md",),
            )

    def test_latest_mimo_response_replaces_old_provisional_tags_but_not_confirmed_tags(self):
        connection = sqlite3.connect(":memory:")
        ensure_schema(connection)
        import_exam_questions(connection, [{
            "question_id": "math1:2026:1:screen-v1",
            "exam_type": "math1",
            "year": 2026,
            "question_no": "1",
            "section": "选择题",
            "score": 4,
            "difficulty_coefficient": 0.8,
            "question_text": "题干",
            "answer": "A",
            "explanation": "解析",
            "knowledge_point_ids": ["old-tag"],
            "source_reference": "2026/math1/page.png",
            "mapping_status": "ai_suggested",
        }], data_version="screen-v1")

        pending_row = {
            "question_id": "math1:2026:1:screen-v1",
            "exam_type": "math1",
            "year": 2026,
            "question_no": "1",
            "section": "选择题",
            "score": 4,
            "difficulty_coefficient": 0.8,
            "question_text": "题干",
            "answer": "A",
            "explanation": "解析",
            "knowledge_point_ids": [],
            "source_reference": "2026/math1/page.png",
            "mapping_status": "pending",
        }
        self.assertEqual(refresh_provisional_question_mappings(connection, [pending_row], "screen-v1"), 1)
        self.assertEqual(
            connection.execute(
                "SELECT mapping_status, knowledge_point_ids FROM math_exam_questions WHERE question_id=?",
                ("math1:2026:1:screen-v1",),
            ).fetchone(),
            ("pending", "[]"),
        )

        mimo_row = {**pending_row, "knowledge_point_ids": ["new-tag"], "mapping_status": "ai_suggested"}
        self.assertEqual(refresh_provisional_question_mappings(connection, [mimo_row], "screen-v1"), 1)
        self.assertEqual(
            connection.execute(
                "SELECT mapping_status, knowledge_point_ids FROM math_exam_questions WHERE question_id=?",
                ("math1:2026:1:screen-v1",),
            ).fetchone(),
            ("ai_suggested", '["new-tag"]'),
        )

        self.assertTrue(confirm_question_mapping(connection, "math1:2026:1:screen-v1", "screen-v1", ("confirmed-tag",)))
        self.assertEqual(refresh_provisional_question_mappings(connection, [mimo_row], "screen-v1"), 0)

    def test_saves_one_model_response_per_screenshot_for_resumable_extraction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "data"
            page_dir = root / "2026" / "screenshots" / "math1"
            page_dir.mkdir(parents=True)
            (page_dir / "pdf_page_0910.png").write_bytes(b"png")
            tasks = discover_screenshot_tasks(root, 2026, "math1")
            output = root / "2026" / "responses" / "math1"
            calls = []

            def extractor(task, prompt):
                calls.append((task.page_name, prompt))
                return '{"questions": []}'

            written = save_extraction_responses(tasks, output, extractor)

            self.assertEqual(calls[0][0], "pdf_page_0910.png")
            self.assertTrue(written[0].exists())
            self.assertEqual(written[0].read_text(encoding="utf-8"), '{"questions": []}')

    def test_can_overwrite_only_named_failed_page_responses_for_retry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "data"
            page_dir = root / "2026" / "screenshots" / "math1"
            response_dir = root / "2026" / "responses" / "math1"
            page_dir.mkdir(parents=True)
            response_dir.mkdir(parents=True)
            (page_dir / "pdf_page_0910.png").write_bytes(b"png")
            (response_dir / "pdf_page_0910.json").write_text('{"broken": true}', encoding="utf-8")
            task = discover_screenshot_tasks(root, 2026, "math1")[0]

            save_extraction_responses((task,), response_dir, lambda *_: '{"questions": []}', force_page_names=(task.page_name,))

            self.assertEqual((response_dir / "pdf_page_0910.json").read_text(encoding="utf-8"), '{"questions": []}')

    def test_retry_unmapped_reprocesses_cached_screenshot_without_repeating_tagged_response(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "data"
            page_dir = root / "2026" / "screenshots" / "math1"
            response_dir = root / "2026" / "responses" / "math1"
            page_dir.mkdir(parents=True)
            response_dir.mkdir(parents=True)
            (page_dir / "pdf_page_0910.png").write_bytes(b"png")
            (page_dir / "pdf_page_0911.png").write_bytes(b"png")
            response_path = response_dir / "pdf_page_0910.json"
            response_path.write_text(
                json.dumps({"questions": [{
                    "question_no": "1", "section": "选择题", "score": 4,
                    "difficulty_coefficient": 0.8, "question_text": "题干", "answer": "A",
                    "knowledge_point_ids": [],
                }]}),
                encoding="utf-8",
            )
            tagged_response_path = response_dir / "pdf_page_0911.json"
            tagged_response_path.write_text(
                json.dumps({"questions": [{
                    "question_no": "1", "section": "选择题", "score": 4,
                    "difficulty_coefficient": 0.8, "question_text": "已标记题", "answer": "A",
                    "knowledge_point_ids": ["limit"],
                }]}, ensure_ascii=False),
                encoding="utf-8",
            )
            calls = []

            def extractor(task, prompt):
                calls.append(task.page_name)
                return '{"questions": [{"question_no": "1", "section": "选择题", "score": 4, "difficulty_coefficient": 0.8, "question_text": "题干", "answer": "A", "knowledge_point_ids": ["limit"]}]}'

            save_extraction_responses(
                discover_screenshot_tasks(root, 2026, "math1"),
                response_dir,
                extractor,
                retry_unmapped=True,
            )

            self.assertEqual(calls, ["pdf_page_0910.png"])
            self.assertIn('"limit"', response_path.read_text(encoding="utf-8"))
            self.assertIn("已标记题", tagged_response_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
