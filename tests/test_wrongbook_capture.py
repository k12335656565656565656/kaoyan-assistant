import unittest

from wrongbook_utils import build_wrongbook_capture, select_quiz_for_wrongbook


class WrongbookCaptureTests(unittest.TestCase):
    def test_select_quiz_for_wrongbook_keeps_scored_quiz_after_active_state_is_cleared(self):
        preserved_quiz = {"success": True, "questions": "Q: preserved question"}

        selected = select_quiz_for_wrongbook(None, preserved_quiz)

        self.assertIs(selected, preserved_quiz)

    def test_build_wrongbook_capture_keeps_question_options_answer_and_explanation(self):
        raw = """Q: What is the derivative of x^2?
A) x
B) 2x
C) x^3
D) 2
ANSWER: B
EXPLAIN: Apply the power rule.
---"""

        captured = build_wrongbook_capture(raw)

        self.assertEqual(
            captured,
            {
                "question": "What is the derivative of x^2?\nA) x\nB) 2x\nC) x^3\nD) 2",
                "correct_answer": "B",
                "explanation": "Apply the power rule.",
            },
        )

    def test_build_wrongbook_capture_uses_fallback_when_quiz_text_is_empty(self):
        captured = build_wrongbook_capture(
            "",
            fallback_question="The original question",
            fallback_correct_answer="The correct answer",
        )

        self.assertEqual(captured["question"], "The original question")
        self.assertEqual(captured["correct_answer"], "The correct answer")
        self.assertEqual(captured["explanation"], "")

    def test_build_wrongbook_capture_only_keeps_the_first_question_block(self):
        raw = """Q: First question
A) First option
ANSWER: A
---
Q: Second question
A) Second option
ANSWER: A
"""

        captured = build_wrongbook_capture(raw)

        self.assertEqual(captured["question"], "First question\nA) First option")
        self.assertEqual(captured["correct_answer"], "A")


if __name__ == "__main__":
    unittest.main()
