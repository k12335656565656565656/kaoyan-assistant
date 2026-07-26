import json
import os
import unittest
from unittest.mock import patch


class ProfessionalQuestionStreamingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("AI_API_KEY", "test-key")
        import knowledge_base

        cls.knowledge_base = knowledge_base

    def test_streaming_helper_concatenates_chunks_and_reports_received_chars(self):
        progress = []
        with patch(
            "knowledge_base.stream_chat_completion",
            return_value=iter(["{\"question\":", "\"AOV\"}"]),
            create=True,
        ):
            result = self.knowledge_base._call_llm_api_stream(
                "generate",
                on_progress=lambda stage, details: progress.append((stage, details.copy())),
            )

        self.assertEqual(result, '{"question":"AOV"}')
        self.assertEqual(
            [item[0] for item in progress],
            ["request_started", "streaming", "streaming"],
        )
        self.assertEqual(progress[-1][1]["received_chars"], len(result))
        self.assertEqual(
            [item[1]["received_chars"] for item in progress if "received_chars" in item[1]],
            [len('{"question":'), len(result)],
        )

    def test_professional_generation_uses_sync_initial_call_with_progress_callback(self):
        point = {
            "knowledge_name": "AOV 网与活动排序",
            "core_definition": "AOV 网用于表达活动之间的先后关系。",
            "keywords_json": json.dumps(["AOV网", "拓扑排序", "入度"], ensure_ascii=False),
        }
        raw = json.dumps(
            {
                "question_type": "application",
                "question": "给定 AOV 网边集 A->B、A->C、B->D、C->D，请写出一种拓扑序列并说明判断依据。",
                "options": [],
                "correct_answer": "",
                "reference_answer": "反复选择入度为 0 的顶点并删除其出边。",
                "grading_points": ["入度为0", "拓扑序列", "有向无环图"],
                "similar_question": "调整一条边后重新判断拓扑序列。",
            },
            ensure_ascii=False,
        )
        progress = []
        with patch.dict(os.environ, {"AI_API_KEY": "test-key", "PROFESSIONAL_QUESTION_REVIEW_ENABLED": "0"}), \
                patch.object(self.knowledge_base, "_call_llm_api_stream") as stream_call, \
                patch.object(self.knowledge_base, "_call_llm_api", return_value=raw) as sync_call:
            generated, warning = self.knowledge_base._generate_professional_question_with_ai(
                point,
                "application",
                progress_callback=lambda stage, details: progress.append((stage, details.copy())),
            )

        self.assertEqual(warning, "")
        self.assertFalse(generated["generation_failed"])
        self.assertIn("拓扑序列", generated["question"])
        sync_call.assert_called_once()
        stream_call.assert_not_called()
        self.assertIn("request_started", [stage for stage, _ in progress])

    def test_progress_renderer_shows_stage_without_partial_json(self):
        class Placeholder:
            def __init__(self):
                self.value = ""

            def markdown(self, value, **_kwargs):
                self.value = value

        placeholder = Placeholder()
        self.knowledge_base._render_professional_question_progress(
            placeholder,
            "streaming",
            {"received_chars": 128},
        )

        self.assertIn("正在生成题目", placeholder.value)
        self.assertIn("已接收 128 个字符", placeholder.value)
        self.assertNotIn('{"question"', placeholder.value)

    def test_question_typewriter_renders_question_and_options_in_order(self):
        class Placeholder:
            def __init__(self):
                self.values = []

            def markdown(self, value, **_kwargs):
                self.values.append(str(value))

            def info(self, value):
                raise AssertionError("typewriter content must not use a fixed info box")

        placeholder = Placeholder()
        self.knowledge_base._render_professional_question_typewriter(
            placeholder,
            {
                "question": "Question AB",
                "options": ["A. Option one", "B. Option two"],
            },
            delay=0,
        )

        self.assertGreater(len(placeholder.values), 3)
        final_value = placeholder.values[-1]
        self.assertIn("Question AB", final_value)
        self.assertLess(final_value.index("A. Option one"), final_value.index("B. Option two"))

    def test_start_professional_study_typewrites_successful_question(self):
        point = {"id": "point-1", "knowledge_name": "AOV"}
        generated = {
            "question": "Question AB",
            "options": [],
            "generation_failed": False,
        }
        placeholder = object()
        state_key = self.knowledge_base._study_state_key(7, "408", "library")
        variant_key = "pk_question_variant_7_408_point-1_application_library"
        self.knowledge_base.st.session_state.pop(state_key, None)
        self.knowledge_base.st.session_state.pop(variant_key, None)
        try:
            with patch.object(
                self.knowledge_base,
                "_question_point_with_retrieval_context",
                return_value=point,
            ), patch.object(
                self.knowledge_base,
                "_generate_professional_question",
                return_value=generated,
            ), patch.object(
                self.knowledge_base,
                "_render_professional_question_typewriter",
            ) as typewriter:
                self.knowledge_base._start_professional_study(
                    7,
                    "408",
                    point,
                    "application",
                    "library",
                    progress_placeholder=placeholder,
                )

            typewriter.assert_called_once_with(placeholder, generated)
            self.assertEqual(
                self.knowledge_base.st.session_state[state_key]["question"],
                "Question AB",
            )
        finally:
            self.knowledge_base.st.session_state.pop(state_key, None)
            self.knowledge_base.st.session_state.pop(variant_key, None)


if __name__ == "__main__":
    unittest.main()
