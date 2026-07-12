import sqlite3
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from repositories.material_repo import (
    create_material,
    ensure_material_schema,
    get_material,
    list_resumable_materials,
    mark_material_status,
    save_confirmed_text,
    save_extraction_result,
    save_workflow_snapshot,
)
from schemas.material_schema import MaterialResult


class MaterialRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_old_material_schema_is_extended_without_losing_rows(self):
        self.conn.execute(
            """CREATE TABLE user_materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subject TEXT,
                filename TEXT,
                chapter_name TEXT,
                file_path TEXT,
                file_type TEXT,
                processing_status TEXT DEFAULT 'pending',
                knowledge_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        self.conn.execute(
            """INSERT INTO user_materials
               (user_id, subject, filename, processing_status)
               VALUES (1, '408综合', 'legacy.pdf', 'pending')"""
        )

        ensure_material_schema(self.conn)

        columns = {
            row[1]
            for row in self.conn.execute("PRAGMA table_info(user_materials)").fetchall()
        }
        self.assertTrue(
            {
                "subject_key",
                "source_type",
                "process_method",
                "raw_extracted_text",
                "extracted_text",
                "confirmed_text",
                "material_result_json",
                "workflow_snapshot_json",
                "content_hash",
                "error_message",
                "updated_at",
            }.issubset(columns)
        )
        legacy = get_material(self.conn, 1)
        self.assertEqual(legacy["filename"], "legacy.pdf")
        self.assertEqual(legacy["material_result"], {})

    def test_material_workflow_can_be_saved_and_resumed(self):
        material = create_material(
            self.conn,
            user_id=7,
            subject="数据结构",
            subject_key="cs_408",
            filename="chapter.pdf",
            file_type="pdf",
        )
        result = MaterialResult(
            source_type="pdf",
            process_method="pdf_text_extract",
            extracted_text="栈是线性表。",
            raw_extracted_text="栈是线性表。",
            confidence=0.98,
        )

        material = save_extraction_result(self.conn, material["id"], result)
        material = save_confirmed_text(
            self.conn, material["id"], "栈是只允许在一端操作的线性表。"
        )
        material = save_workflow_snapshot(
            self.conn,
            material["id"],
            {"step": "draft_review", "draft_ids": ["draft-1"]},
            status="draft_ready",
        )

        self.assertEqual(material["material_result"]["confidence"], 0.98)
        self.assertEqual(material["workflow_snapshot"]["step"], "draft_review")
        self.assertTrue(material["content_hash"])
        resumable = list_resumable_materials(
            self.conn, 7, subject_key="cs_408"
        )
        self.assertEqual([item["id"] for item in resumable], [material["id"]])

        mark_material_status(self.conn, material["id"], "done")
        self.assertEqual(list_resumable_materials(self.conn, 7), [])

    def test_malformed_json_is_returned_as_empty_dict(self):
        material = create_material(self.conn, user_id=1, filename="broken.txt")
        self.conn.execute(
            """UPDATE user_materials
               SET material_result_json='not-json', workflow_snapshot_json='[]'
               WHERE id=?""",
            (material["id"],),
        )

        loaded = get_material(self.conn, material["id"])
        self.assertEqual(loaded["material_result"], {})
        self.assertEqual(loaded["workflow_snapshot"], {})


if __name__ == "__main__":
    unittest.main()
