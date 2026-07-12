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
from repositories.material_repo import create_material


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

    def test_review_content_update_is_persisted(self):
        save_confirmed_knowledge_points(
            self.conn,
            user_id=1,
            points=[{"knowledge_name": "队列", "source_text": "题2：队列先进先出。"}],
            material_meta={"subject": "408综合"},
        )
        self.conn.commit()

        knowledge_id = self.conn.execute("SELECT id FROM user_knowledge LIMIT 1").fetchone()[0]
        update_knowledge_review_content(self.conn, knowledge_id, "复习卡片：Q 队列是什么？A 先进先出。")
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


if __name__ == "__main__":
    unittest.main()
