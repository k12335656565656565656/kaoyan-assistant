import unittest

from professional_knowledge.builtin_408 import BUILTIN_408_SOURCE_TYPE
from services import professional_question_prompts as prompts
from services import professional_question_validator as validator


class ProfessionalQuestionPromptTests(unittest.TestCase):
    def test_blank_prompt_requires_corresponding_non_conflicting_reference(self):
        point = {
            "knowledge_name": "最短路径算法",
            "subject": "数据结构",
            "source_type": BUILTIN_408_SOURCE_TYPE,
        }

        prompt = prompts.build_professional_question_prompt(point, mode="blank", variant=2)

        self.assertIn("reference_answer 必须逐空解释", prompt)
        self.assertIn("每个结论必须与 correct_answer 对应且不得矛盾", prompt)
        self.assertIn("不要考口径不唯一的交换次数", prompt)
        self.assertNotIn("完全一致", prompt)

    def test_408_shortest_path_blueprint_mentions_dijkstra_or_floyd(self):
        point = {
            "knowledge_name": "最短路径算法",
            "subject": "数据结构",
            "keywords_json": '["Dijkstra", "Floyd", "最短路径"]',
            "source_type": BUILTIN_408_SOURCE_TYPE,
        }

        blueprint = prompts.format_408_blueprints(point, mode="blank", variant=1)

        self.assertIn("408科目判定：数据结构", blueprint)
        self.assertTrue("Dijkstra" in blueprint or "Floyd" in blueprint)
        self.assertIn("边集", blueprint)


class ProfessionalQuestionValidatorTests(unittest.TestCase):
    def test_validator_accepts_valid_shortest_path_blank(self):
        generated = {
            "question_type": "blank",
            "question": "带权有向图从 A 到 D 的边有 A->B=2、A->C=6、B->D=3、C->D=1。先确定的中间顶点是 ______，A 到 D 的最短路径长度为 ______。",
            "options": [],
            "correct_answer": "B；5",
            "reference_answer": "第一空填 B，因为 Dijkstra 初始距离中 B 的距离 2 最小，应先确定 B。第二空填 5，经过 B 松弛后 A 到 D 的距离为 2+3=5，小于经 C 的 7。",
            "grading_points": ["先确定最小距离顶点", "完成松弛", "写出最短路径长度"],
        }

        self.assertTrue(
            validator.is_valid_professional_question_for_point(
                generated,
                "blank",
                {"knowledge_name": "最短路径算法", "subject": "数据结构"},
            )
        )

    def test_validator_rejects_contradictory_short_numeric_answer(self):
        generated = {
            "question_type": "blank",
            "question": "带权有向图从 A 到 D 的边有 A->B=2、A->C=6、B->D=3、C->D=1。A 到 D 的最短路径长度为 ______。",
            "options": [],
            "correct_answer": "7",
            "reference_answer": "空处填 5，因为 A->B->D 的路径长度为 2+3=5，小于 A->C->D 的 7。",
            "grading_points": ["完成松弛", "写出最短路径长度"],
        }

        self.assertFalse(
            validator.is_valid_professional_question_for_point(
                generated,
                "blank",
                {"knowledge_name": "最短路径算法", "subject": "数据结构"},
            )
        )

    def test_validator_accepts_parentheses_blank_marker(self):
        generated = {
            "question_type": "blank",
            "question": "在 Dijkstra 算法中，若存在负权边但无负权回路，应改用（ ）算法处理单源最短路径。",
            "options": [],
            "correct_answer": "Bellman-Ford",
            "reference_answer": "空处填 Bellman-Ford。Dijkstra 依赖每次确定的最短距离不会再变小，负权边会破坏这个性质；Bellman-Ford 通过多轮松弛处理含负权边的单源最短路径。",
            "grading_points": ["识别负权条件", "说明 Dijkstra 限制", "给出替代算法"],
        }

        self.assertEqual(validator.blank_marker_count(generated["question"]), 1)
        self.assertTrue(
            validator.is_valid_professional_question_for_point(
                generated,
                "blank",
                {"knowledge_name": "最短路径算法", "subject": "数据结构"},
            )
        )


if __name__ == "__main__":
    unittest.main()
