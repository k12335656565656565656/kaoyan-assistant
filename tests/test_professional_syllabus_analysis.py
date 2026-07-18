import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from repositories.material_repo import create_material
from repositories.professional_syllabus_repo import (
    create_syllabus_analysis,
    get_syllabus_analysis,
)
from services.professional_syllabus_analysis_service import run_syllabus_analysis_job


class ProfessionalSyllabusAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "memory.db"
        self.original_api_key = os.environ.get("AI_API_KEY")
        os.environ["AI_API_KEY"] = ""

    def tearDown(self):
        if self.original_api_key is None:
            os.environ.pop("AI_API_KEY", None)
        else:
            os.environ["AI_API_KEY"] = self.original_api_key
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_analysis_matches_uploaded_syllabus_to_builtin_408_points(self):
        conn = sqlite3.connect(self.db_path)
        try:
            material = create_material(
                conn,
                user_id=1,
                subject="408综合",
                filename="目标院校408考试大纲.txt",
                chapter_name="目标院校408考试大纲",
                confirmed_text=(
                    "数据结构重点考 AOV 网、拓扑排序、B 树和 B+ 树。"
                    "计算机组成原理重点关注 Cache 映射、ALU 标志位。"
                    "计算机网络要求掌握 TCP 拥塞控制和子网划分。"
                ),
                processing_status="done",
            )
            analysis = create_syllabus_analysis(
                conn,
                user_id=1,
                subject="408综合",
                source_ids=[material["id"]],
            )
            conn.commit()
        finally:
            conn.close()

        run_syllabus_analysis_job(str(self.db_path), analysis["id"])

        conn = sqlite3.connect(self.db_path)
        try:
            saved = get_syllabus_analysis(conn, analysis["id"])
        finally:
            conn.close()

        self.assertEqual(saved["status"], "completed")
        self.assertTrue(saved["school_focus"])
        self.assertTrue(saved["priority_points"])
        self.assertTrue(saved["phase_plan"])
        names = " ".join(item["knowledge_name"] for item in saved["priority_points"])
        self.assertIn("AOV", names)
        self.assertIn("Cache", names)


if __name__ == "__main__":
    unittest.main()
