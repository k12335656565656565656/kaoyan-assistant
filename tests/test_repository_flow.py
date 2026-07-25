import sqlite3
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from repositories.knowledge_repo import (
    ensure_knowledge_schema,
    list_user_knowledge_points,
    save_confirmed_knowledge_points,
    update_knowledge_review_content,
)
from repositories.material_repo import create_material, delete_material_source


class RepositoryFlowTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        ensure_knowledge_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_confirmed_points_can_be_saved_and_listed(self):
        saved = save_confirmed_knowledge_points(
            self.conn,
            user_id=1,
            points=[
                {
                    "knowledge_name": "栈",
                    "knowledge_type": "概念",
                    "subject": "408综合",
                    "chapter_name": "数据结构",
                    "core_definition": "栈是只允许在一端插入和删除的线性表。",
                    "source_text": "题1：栈是只允许在一端插入和删除的线性表。",
                    "source_page": "第1页",
                    "source_location": "题1",
                    "keywords": ["栈", "线性表"],
                }
            ],
            material_meta={
                "material_id": 1,
                "subject": "408综合",
                "chapter_name": "数据结构",
                "source_type": "pdf",
                "process_method": "pdf_text_extract",
                "material_filename": "sample.pdf",
            },
        )
        self.conn.commit()

        points = list_user_knowledge_points(self.conn, user_id=1, limit=20)
        self.assertEqual(saved, 1)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["knowledge_name"], "栈")
        self.assertEqual(points[0]["source_page"], "第1页")

    def test_knowledge_list_can_be_scoped_to_one_subject(self):
        for subject, name in (("408综合", "栈"), ("医学考研", "肺炎")):
            save_confirmed_knowledge_points(
                self.conn,
                user_id=1,
                points=[{"knowledge_name": name, "source_text": f"原文：{name}"}],
                material_meta={"subject": subject},
                strict=False,
            )

        points = list_user_knowledge_points(
            self.conn,
            user_id=1,
            limit=20,
            subject="408综合",
        )

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["subject"], "408综合")
        self.assertEqual(points[0]["knowledge_name"], "栈")

    def test_knowledge_list_can_be_scoped_to_selected_materials(self):
        first_material = create_material(
            self.conn,
            user_id=1,
            subject="408综合",
            filename="data-structure.pdf",
            file_type="pdf",
        )
        second_material = create_material(
            self.conn,
            user_id=1,
            subject="408综合",
            filename="network.pdf",
            file_type="pdf",
        )
        for material, name in ((first_material, "栈"), (second_material, "TCP拥塞控制")):
            save_confirmed_knowledge_points(
                self.conn,
                user_id=1,
                points=[{"knowledge_name": name, "source_text": f"原文：{name}"}],
                material_meta={
                    "material_id": material["id"],
                    "subject": "408综合",
                    "material_filename": material["filename"],
                },
                strict=False,
            )

        points = list_user_knowledge_points(
            self.conn,
            user_id=1,
            subject="408综合",
            material_ids=[first_material["id"]],
        )

        self.assertEqual([point["knowledge_name"] for point in points], ["栈"])
        self.assertEqual(
            list_user_knowledge_points(
                self.conn,
                user_id=1,
                subject="408综合",
                material_ids=[],
            ),
            [],
        )

    def test_review_content_update_is_persisted(self):
        save_confirmed_knowledge_points(
            self.conn,
            user_id=1,
            points=[{"knowledge_name": "队列", "source_text": "题2：队列先进先出。"}],
            material_meta={"subject": "408综合"},
        )
        self.conn.commit()

        knowledge_id = self.conn.execute("SELECT id FROM user_knowledge LIMIT 1").fetchone()[0]
        update_knowledge_review_content(
            self.conn,
            7,
            knowledge_id,
            "不应写入",
        )
        update_knowledge_review_content(
            self.conn,
            1,
            knowledge_id,
            "复习卡片：Q 队列是什么？A 先进先出。",
        )
        self.conn.commit()

        row = self.conn.execute(
            "SELECT review_content, review_generated_at FROM user_knowledge WHERE id=?",
            (knowledge_id,),
        ).fetchone()
        self.assertIn("复习卡片", row[0])
        self.assertIsNotNone(row[1])

    def test_strict_save_rejects_point_without_source_evidence(self):
        with self.assertRaisesRegex(ValueError, "拒绝入库"):
            save_confirmed_knowledge_points(
                self.conn,
                user_id=1,
                points=[
                    {
                        "knowledge_name": "不完整知识点",
                        "core_definition": "只有总结，没有原文证据。",
                        "source_text": "",
                    }
                ],
                material_meta={"subject": "408综合"},
                strict=True,
            )
        count = self.conn.execute("SELECT COUNT(*) FROM user_knowledge").fetchone()[0]
        self.assertEqual(count, 0)

    def test_non_strict_save_skips_empty_placeholder_point(self):
        saved = save_confirmed_knowledge_points(
            self.conn,
            user_id=1,
            points=[
                {
                    "knowledge_name": "未命名知识点",
                    "core_definition": "",
                    "source_text": "",
                }
            ],
            material_meta={"subject": "408综合"},
            strict=False,
        )

        self.assertEqual(saved, 0)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM user_knowledge").fetchone()[0],
            0,
        )

    def test_repository_keeps_useful_experience_and_rejects_noise(self):
        saved = save_confirmed_knowledge_points(
            self.conn,
            user_id=1,
            points=[
                {
                    "knowledge_name": "候选知识点1",
                    "core_definition": "更多计算机考研资料和信息，请扫码咨询>>> 考场上应预留15分钟检查，并及时跳过异常题。",
                    "source_text": "更多计算机考研资料和信息，请扫码咨询>>> 考场时间控制在2小时45分钟，最后15分钟检查。",
                },
                {
                    "knowledge_name": "个人背景 本科",
                    "core_definition": "本科某双非，报考院校某大学，初试成绩总分333，无科研无竞赛。",
                    "source_text": "个人背景与成绩介绍。",
                },
                {
                    "knowledge_name": "考研数学复习阶段规划",
                    "core_definition": "数学一分为基础、强化和冲刺阶段。",
                    "source_text": "数一需要分阶段复习。",
                },
            ],
            material_meta={"subject": "408综合"},
            strict=False,
        )

        self.assertEqual(saved, 1)
        row = self.conn.execute(
            "SELECT knowledge_name, knowledge_type, core_definition, source_text FROM user_knowledge"
        ).fetchone()
        self.assertEqual(row[0], "考场时间分配与跳题策略")
        self.assertEqual(row[1], "备考经验")
        self.assertNotIn("扫码咨询", row[2])
        self.assertNotIn("扫码咨询", row[3])

    def test_repository_rejects_math_book_cover_metadata(self):
        saved = save_confirmed_knowledge_points(
            self.conn,
            user_id=1,
            points=[
                {"knowledge_name": "中国农业出版社", "core_definition": "中国农业出版社", "source_text": "中国农业出版社"},
                {"knowledge_name": "编著◎武忠祥", "core_definition": "编著◎武忠祥", "source_text": "编著◎武忠祥"},
                {
                    "knowledge_name": "函数性质判断（题1）",
                    "knowledge_type": "题目",
                    "core_definition": "判断函数的奇偶性、周期性和有界性。",
                    "source_text": "题1：判断函数的奇偶性。A. 偶函数 B. 奇函数",
                },
            ],
            material_meta={"subject": "数二"},
            strict=False,
        )

        self.assertEqual(saved, 1)
        row = self.conn.execute("SELECT knowledge_name, knowledge_type FROM user_knowledge").fetchone()
        self.assertEqual(row, ("函数性质判断（题1）", "题目"))

    def test_duplicate_save_is_ignored_and_material_count_does_not_drift(self):
        material = create_material(
            self.conn,
            user_id=1,
            subject="408综合",
            subject_key="cs_408",
            filename="stack.pdf",
            file_type="pdf",
        )
        first_point = {
            "knowledge_name": "栈",
            "subject": "408综合",
            "chapter_name": "数据结构",
            "core_definition": "栈是只允许在一端操作的线性表。",
            "source_text": "栈是只允许在一端操作的线性表。",
            "keywords": ["栈", "LIFO"],
        }
        equivalent_point = {
            **first_point,
            "core_definition": " 栈是只允许在一端操作的线性表。 ",
            "keywords": ["LIFO", " 栈 "],
        }
        material_meta = {
            "material_id": material["id"],
            "subject": "408综合",
            "subject_key": "cs_408",
            "chapter_name": "数据结构",
            "material_filename": "stack.pdf",
        }

        first_saved = save_confirmed_knowledge_points(
            self.conn, 1, [first_point], material_meta=material_meta
        )
        duplicate_saved = save_confirmed_knowledge_points(
            self.conn, 1, [equivalent_point], material_meta=material_meta
        )

        self.assertEqual(first_saved, 1)
        self.assertEqual(duplicate_saved, 0)
        row = self.conn.execute(
            "SELECT COUNT(*), subject_key FROM user_knowledge WHERE user_id=1"
        ).fetchone()
        self.assertEqual(row, (1, "cs_408"))
        material_row = self.conn.execute(
            """SELECT processing_status, knowledge_count
               FROM user_materials WHERE id=?""",
            (material["id"],),
        ).fetchone()
        self.assertEqual(material_row, ("done", 1))

    def test_partial_save_updates_count_without_finalizing_material(self):
        material = create_material(
            self.conn,
            user_id=1,
            subject="408综合",
            filename="partial.pdf",
            processing_status="drafted",
        )
        saved = save_confirmed_knowledge_points(
            self.conn,
            1,
            [
                {
                    "knowledge_name": "部分确认知识点",
                    "core_definition": "这是一条已确认定义。",
                    "source_text": "原文：这是一条已确认定义。",
                }
            ],
            material_meta={"material_id": material["id"], "subject": "408综合"},
            strict=True,
            finalize_material=False,
        )

        self.assertEqual(saved, 1)
        status, count = self.conn.execute(
            "SELECT processing_status, knowledge_count FROM user_materials WHERE id=?",
            (material["id"],),
        ).fetchone()
        self.assertEqual(status, "drafted")
        self.assertEqual(count, 1)

    def test_old_knowledge_schema_is_migrated_without_losing_data(self):
        legacy_conn = sqlite3.connect(":memory:")
        try:
            legacy_conn.execute(
                """CREATE TABLE user_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    material_id INTEGER,
                    subject TEXT,
                    chapter_name TEXT,
                    knowledge_name TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            legacy_conn.execute(
                """INSERT INTO user_knowledge
                   (user_id, subject, knowledge_name, content)
                   VALUES (1, '408综合', '旧知识点', '旧内容')"""
            )

            ensure_knowledge_schema(legacy_conn)

            columns = {
                row[1]
                for row in legacy_conn.execute(
                    "PRAGMA table_info(user_knowledge)"
                ).fetchall()
            }
            self.assertTrue({"subject_key", "ingest_key"}.issubset(columns))
            indexes = legacy_conn.execute(
                "PRAGMA index_list(user_knowledge)"
            ).fetchall()
            self.assertTrue(
                any(
                    row[1] == "ux_user_knowledge_user_ingest_key" and row[2] == 1
                    for row in indexes
                )
            )
            self.assertEqual(
                legacy_conn.execute(
                    "SELECT knowledge_name FROM user_knowledge WHERE id=1"
                ).fetchone()[0],
                "旧知识点",
            )
        finally:
            legacy_conn.close()

    def test_delete_source_removes_derived_knowledge_but_preserves_wrong_question(self):
        material = create_material(
            self.conn,
            user_id=1,
            subject="408综合",
            filename="duplicate.pdf",
        )
        save_confirmed_knowledge_points(
            self.conn,
            1,
            [{"knowledge_name": "页表", "source_text": "提纲：页表"}],
            material_meta={"material_id": material["id"], "subject": "408综合"},
        )
        knowledge_id = self.conn.execute(
            "SELECT id FROM user_knowledge WHERE material_id=?", (material["id"],)
        ).fetchone()[0]
        self.conn.execute(
            """CREATE TABLE user_wrong_questions (
                   id INTEGER PRIMARY KEY, user_id INTEGER, knowledge_id INTEGER, question TEXT
               )"""
        )
        self.conn.execute(
            """CREATE TABLE user_review_records (
                   id INTEGER PRIMARY KEY, user_id INTEGER, knowledge_id INTEGER
               )"""
        )
        self.conn.execute(
            "INSERT INTO user_wrong_questions VALUES (1, 1, ?, '页表错题')", (knowledge_id,)
        )
        self.conn.execute(
            "INSERT INTO user_review_records VALUES (1, 1, ?)", (knowledge_id,)
        )

        deleted = delete_material_source(self.conn, 1, material["id"])

        self.assertTrue(deleted["deleted"])
        self.assertEqual(deleted["knowledge_deleted"], 1)
        self.assertEqual(
            self.conn.execute("SELECT question, knowledge_id FROM user_wrong_questions").fetchone(),
            ("页表错题", None),
        )
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM user_review_records").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM user_materials").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
