import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_DIR = Path(__file__).resolve().parents[1]


def _find_by_label(elements, label, occurrence=0):
    matches = [element for element in elements if element.label == label]
    if len(matches) <= occurrence:
        raise AssertionError(f"未找到控件：{label}（序号 {occurrence}）")
    return matches[occurrence]


class ProfessionalKnowledgeUiFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "memory.db"
        self.original_memory_db_env = os.environ.get("MEMORY_DB")
        self.original_api_key_env = os.environ.get("AI_API_KEY")
        os.environ["MEMORY_DB"] = str(self.db_path)
        os.environ["AI_API_KEY"] = ""

        import knowledge_base
        import professional_knowledge.catalog as catalog
        import repositories.wrong_question_repo as wrong_question_repo
        import services.professional_knowledge_task_service as task_service

        self.knowledge_base = knowledge_base
        self.catalog = catalog
        self.wrong_question_repo = wrong_question_repo
        self.task_service = task_service
        self.original_memory_db = knowledge_base.MEMORY_DB
        self.original_wrong_question_db = wrong_question_repo.MEMORY_DB
        self.original_custom_config = catalog.CUSTOM_SUBJECTS_CONFIG_PATH
        self.original_tasks_dir = task_service.TASKS_DIR
        self.original_llm_call = knowledge_base._call_llm_api

        knowledge_base.MEMORY_DB = str(self.db_path)
        wrong_question_repo.MEMORY_DB = str(self.db_path)
        catalog.CUSTOM_SUBJECTS_CONFIG_PATH = self.temp_dir / "custom_subjects.json"
        task_service.TASKS_DIR = self.temp_dir / "tasks"

    def tearDown(self):
        self.knowledge_base.MEMORY_DB = self.original_memory_db
        self.wrong_question_repo.MEMORY_DB = self.original_wrong_question_db
        self.catalog.CUSTOM_SUBJECTS_CONFIG_PATH = self.original_custom_config
        self.task_service.TASKS_DIR = self.original_tasks_dir
        self.knowledge_base._call_llm_api = self.original_llm_call
        if self.original_memory_db_env is None:
            os.environ.pop("MEMORY_DB", None)
        else:
            os.environ["MEMORY_DB"] = self.original_memory_db_env
        if self.original_api_key_env is None:
            os.environ.pop("AI_API_KEY", None)
        else:
            os.environ["AI_API_KEY"] = self.original_api_key_env
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _run_app(self):
        app = AppTest.from_file(str(PROJECT_DIR / "app_kb.py"), default_timeout=30).run()
        if app.exception:
            raise AssertionError(app.exception)
        return app

    def _paste_material(self, app, text=None):
        _find_by_label(app.text_input, "章节 / 文件主题", occurrence=1).set_value("管理学 - 决策理论")
        _find_by_label(app.text_area, "粘贴文本").set_value(
            text
            or (
                "题1：决策是管理者识别问题、比较备选方案并作出选择的过程。"
                "有限理性会受到信息、时间和认知能力约束。"
            )
        )
        _find_by_label(app.button, "确认文本并开始识别").click().run()
        if app.exception:
            raise AssertionError(app.exception)
        return app

    def test_confirmed_text_survives_restart_and_can_resume(self):
        app = self._paste_material(self._run_app())
        _find_by_label(app.button, "保存文本，稍后继续").click().run()
        if app.exception:
            raise AssertionError(app.exception)

        with closing(sqlite3.connect(self.db_path)) as conn:
            status, confirmed_text = conn.execute(
                "SELECT processing_status, confirmed_text FROM user_materials"
            ).fetchone()
        self.assertEqual(status, "text_confirmed")
        self.assertIn("有限理性", confirmed_text)

        restarted = self._run_app()
        _find_by_label(restarted.button, "继续处理这份资料").click().run()
        if restarted.exception:
            raise AssertionError(restarted.exception)
        preview = _find_by_label(restarted.text_area, "清洗后 / 可继续修正")
        self.assertIn("有限理性", preview.value)

    def test_draft_snapshot_survives_restart(self):
        self.knowledge_base._call_llm_api = lambda *args, **kwargs: (
            _ for _ in ()
        ).throw(RuntimeError("offline test"))
        app = self._paste_material(self._run_app())
        _find_by_label(app.button, "文本已核对，生成候选知识点").click().run()
        if app.exception:
            raise AssertionError(app.exception)

        with closing(sqlite3.connect(self.db_path)) as conn:
            status, snapshot_raw = conn.execute(
                "SELECT processing_status, workflow_snapshot_json FROM user_materials"
            ).fetchone()
        snapshot = json.loads(snapshot_raw)
        self.assertEqual(status, "drafted")
        self.assertTrue(snapshot["remaining_drafts"])

        restarted = self._run_app()
        _find_by_label(restarted.button, "继续处理这份资料").click().run()
        if restarted.exception:
            raise AssertionError(restarted.exception)
        pending = _find_by_label(restarted.metric, "待确认")
        self.assertGreaterEqual(int(pending.value), 1)

        _find_by_label(restarted.button, "确认全部").click().run()
        if restarted.exception:
            raise AssertionError(restarted.exception)
        _find_by_label(restarted.button, "保存已确认知识点到私有知识库").click().run()
        if restarted.exception:
            raise AssertionError(restarted.exception)
        with closing(sqlite3.connect(self.db_path)) as conn:
            knowledge_count = conn.execute("SELECT COUNT(*) FROM user_knowledge").fetchone()[0]
            material_status, material_count = conn.execute(
                "SELECT processing_status, knowledge_count FROM user_materials"
            ).fetchone()
        self.assertGreaterEqual(knowledge_count, 1)
        self.assertEqual(material_status, "done")
        self.assertEqual(material_count, knowledge_count)

    def test_custom_subject_wizard_selects_new_subject(self):
        app = self._run_app()
        _find_by_label(app.text_input, "专业课名称 *").set_value("管理学原理")
        _find_by_label(app.text_input, "考试代码（可选）").set_value("803")
        _find_by_label(app.text_area, "希望系统重点识别什么（可选）").set_value(
            "优先识别理论流派、代表人物和易混点。"
        )
        _find_by_label(app.button, "创建并开始导入资料").click().run()
        if app.exception:
            raise AssertionError(app.exception)

        subject_selector = _find_by_label(app.selectbox, "学科", occurrence=0)
        self.assertIn("管理学原理", subject_selector.options)
        self.assertEqual(subject_selector.value, "管理学原理")
        self.assertTrue(self.catalog.CUSTOM_SUBJECTS_CONFIG_PATH.exists())

    def test_partial_save_remains_resumable_with_remaining_draft(self):
        self.knowledge_base._call_llm_api = lambda *args, **kwargs: (
            _ for _ in ()
        ).throw(RuntimeError("offline test"))
        source_text = (
            "=== 第1页 ===\n题1：决策是从多个备选方案中作出选择的过程。\n\n"
            "=== 第2页 ===\n题2：有限理性受到信息、时间和认知能力约束。"
        )
        app = self._paste_material(self._run_app(), text=source_text)
        _find_by_label(app.button, "文本已核对，生成候选知识点").click().run()
        if app.exception:
            raise AssertionError(app.exception)
        self.assertGreaterEqual(int(_find_by_label(app.metric, "待确认").value), 2)

        _find_by_label(app.button, "确认并加入待保存").click().run()
        if app.exception:
            raise AssertionError(app.exception)
        _find_by_label(app.button, "保存已确认知识点到私有知识库").click().run()
        if app.exception:
            raise AssertionError(app.exception)

        with closing(sqlite3.connect(self.db_path)) as conn:
            status = conn.execute("SELECT processing_status FROM user_materials").fetchone()[0]
            saved_count = conn.execute("SELECT COUNT(*) FROM user_knowledge").fetchone()[0]
        self.assertEqual(status, "drafted")
        self.assertEqual(saved_count, 1)

        restarted = self._run_app()
        _find_by_label(restarted.button, "继续处理这份资料").click().run()
        if restarted.exception:
            raise AssertionError(restarted.exception)
        self.assertGreaterEqual(int(_find_by_label(restarted.metric, "待确认").value), 1)

        _find_by_label(restarted.button, "删除当前草稿").click().run()
        if restarted.exception:
            raise AssertionError(restarted.exception)
        with closing(sqlite3.connect(self.db_path)) as conn:
            final_status = conn.execute(
                "SELECT processing_status FROM user_materials"
            ).fetchone()[0]
        self.assertEqual(final_status, "done")


if __name__ == "__main__":
    unittest.main()
