import re
import json
from datetime import datetime


SUBJECT_ALIASES = {
    "高数": "数学",
    "数学": "数学",
    "英语": "英语",
    "专业课": "专业课",
    "专业": "专业课",
}

_REASONING_LEAK_MARKERS = (
    "<think",
    "</think",
    "reasoning_content",
    "用户要求",
    "我需要先",
    "让我先",
    "我的思考",
    "思考过程",
    "分析一下用户",
    "the user",
    "i need to",
    "let's think",
    "we need to",
    "internal reasoning",
)


def _contains_reasoning_leak(text):
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _REASONING_LEAK_MARKERS)


def _safe_unstructured_final_answer(text):
    """Return a provider final answer when it is safe but omitted the required envelope."""
    answer = re.sub(r"^\s*```(?:markdown|text)?\s*|\s*```\s*$", "", text or "", flags=re.I).strip()
    if not answer or len(answer) > 6000 or _contains_reasoning_leak(answer):
        return ""
    # A partial protocol is not a trustworthy answer; do not silently merge formats.
    if re.search(r"\[(?:DESCRIPTION|ANSWER|KNOWLEDGE)\b", answer, re.I):
        return ""
    return answer


def extract_final_message_content(message):
    """Return only the provider's final response, never hidden reasoning."""
    content = (message or {}).get("content")
    return content.strip() if isinstance(content, str) else ""


def parse_smart_answer_output(text):
    """Accept the strict final-answer envelope used by the Smart Answer view.
    Supports both [DESCRIPTION]/[ANSWER]/[KNOWLEDGE] (new) and [ANSWER]/[KNOWLEDGE] (legacy)."""
    # 新格式：带题目说明
    match = re.fullmatch(
        r"\s*\[DESCRIPTION\]\s*([\s\S]*?)\s*\[ANSWER\]\s*([\s\S]*?)\s*\[KNOWLEDGE\]\s*([\s\S]*?)\s*",
        text or "",
        re.I,
    )
    if match:
        description = match.group(1).strip()
        answer = match.group(2).strip()
        knowledge_text = match.group(3).strip()
        if not answer or len(answer) > 6000 or _contains_reasoning_leak(answer):
            return {"answer": "", "knowledge": [], "quiz": "", "description": ""}
        knowledge = [item.strip() for item in re.split(r"[,，]", knowledge_text) if item.strip()]
        return {"answer": answer, "knowledge": knowledge[:12], "quiz": "", "description": description}

    # 旧格式兼容：无题目说明
    match = re.fullmatch(
        r"\s*\[ANSWER\]\s*([\s\S]*?)\s*\[KNOWLEDGE\]\s*([\s\S]*?)\s*",
        text or "",
        re.I,
    )
    if not match:
        fallback_answer = _safe_unstructured_final_answer(text)
        return {"answer": fallback_answer, "knowledge": [], "quiz": "", "description": ""}
    answer = match.group(1).strip()
    knowledge_text = match.group(2).strip()
    if not answer or len(answer) > 6000 or _contains_reasoning_leak(answer):
        return {"answer": "", "knowledge": [], "quiz": "", "description": ""}
    knowledge = [item.strip() for item in re.split(r"[,，]", knowledge_text) if item.strip()]
    return {"answer": answer, "knowledge": knowledge[:12], "quiz": "", "description": ""}


def parse_wrongbook_ai_question(text):
    """Accept only one exact <question> payload and reject model meta-reasoning."""
    match = re.fullmatch(r"\s*<question>\s*([\s\S]*?)\s*</question>\s*", text or "", re.I)
    if not match:
        return ""
    question = match.group(1).strip()
    if not question or len(question) > 2000 or _contains_reasoning_leak(question):
        return ""
    return question


def parse_wrongbook_ai_answer(text):
    """Parse a strict description/answer/explanation triple without reasoning-content fallbacks.
    Also backward-compatible with legacy answer/explanation format (no description)."""
    cleaned = re.sub(r"^\s*```(?:xml|html|text)?\s*|\s*```\s*$", "", text or "", flags=re.I)
    # 新格式：带题目说明
    match = re.fullmatch(
        r"\s*<description>\s*([\s\S]*?)\s*</description>\s*"
        r"<answer>\s*([\s\S]*?)\s*</answer>\s*"
        r"<explanation>\s*([\s\S]*?)\s*</explanation>\s*",
        cleaned,
        re.I,
    )
    if match:
        description = match.group(1).strip()
        answer = match.group(2).strip()
        explanation = match.group(3).strip()
        if not answer or not explanation:
            return None
        if len(answer) > 400 or len(explanation) > 2000:
            return None
        if _contains_reasoning_leak(answer) or _contains_reasoning_leak(explanation):
            return None
        return {"answer": answer, "explanation": explanation, "description": description}

    # 旧格式兼容：无题目说明
    match = re.fullmatch(
        r"\s*<answer>\s*([\s\S]*?)\s*</answer>\s*"
        r"<explanation>\s*([\s\S]*?)\s*</explanation>\s*",
        cleaned,
        re.I,
    )
    if not match:
        return None
    answer = match.group(1).strip()
    explanation = match.group(2).strip()
    if not answer or not explanation:
        return None
    if len(answer) > 400 or len(explanation) > 2000:
        return None
    if _contains_reasoning_leak(answer) or _contains_reasoning_leak(explanation):
        return None
    return {"answer": answer, "explanation": explanation, "description": ""}


def split_wrongbook_answer_explanation(correct_answer, explanation=""):
    """Split legacy combined answer text while preserving an explicit explanation."""
    answer = str(correct_answer or "").strip()
    explicit_explanation = str(explanation or "").strip()
    if explicit_explanation:
        return answer, explicit_explanation
    match = re.match(
        r"^([\s\S]*?)\s*(?:\n\s*){1,2}(?:解析|解答|EXPLAIN)\s*[:：]\s*([\s\S]+)$",
        answer,
        re.I,
    )
    if not match:
        return answer, ""
    return match.group(1).strip(), match.group(2).strip()


def select_quiz_for_wrongbook(active_quiz=None, preserved_quiz=None):
    """Choose the newest usable quiz, retaining a scored quiz after active state is cleared."""
    for quiz in (active_quiz, preserved_quiz):
        if isinstance(quiz, dict) and str(quiz.get("questions") or "").strip():
            return quiz
    return None


def build_wrongbook_capture(
    raw_text,
    *,
    fallback_question="",
    fallback_correct_answer="",
    fallback_explanation="",
):
    """Extract question/options, answer, and explanation from a generated quiz block."""
    raw = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
    question_lines = []
    option_lines = []
    answer = ""
    explanation_lines = []
    mode = ""

    option_pattern = re.compile(r"^[A-E]\s*(?:[).\u3001]|[:\uff1a])\s*(.*)$", re.I)
    answer_pattern = re.compile(r"^(?:ANSWER|\u7b54\u6848)\s*[:\uff1a]\s*(.*)$", re.I)
    explain_pattern = re.compile(r"^(?:EXPLAIN|\u89e3\u6790|\u89e3\u7b54)\s*[:\uff1a]\s*(.*)$", re.I)
    question_pattern = re.compile(r"^(?:Q|QUESTION|\u95ee\u9898)\s*[:\uff1a]?\s*(.*)$", re.I)
    question_blocks = [
        block for block in raw.split("---")
        if any(question_pattern.match(line.strip()) for line in block.split("\n"))
    ]
    if question_blocks:
        raw = question_blocks[0]

    for raw_line in raw.split("\n"):
        line = raw_line.strip()
        if not line or line == "---":
            continue
        question_match = question_pattern.match(line)
        if question_match:
            mode = "question"
            if question_match.group(1).strip():
                question_lines.append(question_match.group(1).strip())
            continue
        option_match = option_pattern.match(line)
        if option_match:
            mode = "options"
            label = line[: line.find(option_match.group(1))].strip()
            option_lines.append(f"{label} {option_match.group(1).strip()}".strip())
            continue
        answer_match = answer_pattern.match(line)
        if answer_match:
            mode = "answer"
            answer = answer_match.group(1).strip()
            continue
        explain_match = explain_pattern.match(line)
        if explain_match:
            mode = "explanation"
            if explain_match.group(1).strip():
                explanation_lines.append(explain_match.group(1).strip())
            continue
        if mode == "question":
            question_lines.append(line)
        elif mode == "explanation":
            explanation_lines.append(line)

    question = "\n".join(question_lines + option_lines).strip()
    if not question:
        question = str(fallback_question or "").strip()
    if not question and raw.strip():
        question = raw.strip()

    return {
        "question": question,
        "correct_answer": answer or str(fallback_correct_answer or "").strip(),
        "explanation": "\n".join(explanation_lines).strip()
        or str(fallback_explanation or "").strip(),
    }


def detect_subject(text):
    tl = (text or "").lower()
    if any(k in tl for k in ["英语", "翻译", "作文", "词汇", "完形", "长难句", "letter", "essay", "reading", "writing"]):
        return "英语"
    if any(k in tl for k in ["数据结构", "操作系统", "组成原理", "计算机网络", "408", "tcp", "cache", "流水线", "死锁", "虚拟内存", "拥塞控制"]):
        return "专业课"
    return "数学"


def normalize_wrongbook_payload(payload):
    payload = payload or {}
    question = str(payload.get("question", "") or "").strip()
    if not question:
        return {"ok": False, "error": "请先填写题目"}

    raw_subject = str(payload.get("subject", "") or "").strip()
    subject = SUBJECT_ALIASES.get(raw_subject, raw_subject or detect_subject(question))
    if subject not in {"数学", "英语", "专业课"}:
        subject = detect_subject(question)

    try:
        error_count = int(payload.get("errorCount", 1) or 1)
    except (TypeError, ValueError):
        error_count = 1
    error_count = max(1, min(error_count, 5))

    raw_images = payload.get("images", [])
    images = []
    if isinstance(raw_images, list):
        images = [
            image for image in raw_images[:8]
            if isinstance(image, str) and image.startswith("data:image/")
        ]

    return {
        "ok": True,
        "subject": subject,
        "question": question,
        "myAnswer": str(payload.get("myAnswer", payload.get("user_answer", "")) or "").strip(),
        "correctAnswer": str(payload.get("correctAnswer", payload.get("correct_answer", "")) or "").strip(),
        "explanation": str(payload.get("explanation", "") or "").strip(),
        "errorCount": error_count,
        "images": images,
    }


def _space_fold(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def save_wrongbook_payload(conn, user_id, payload):
    data = normalize_wrongbook_payload(payload)
    if not data.get("ok"):
        return data

    question_key = _space_fold(data["question"])
    candidates = conn.execute(
        """
        SELECT id, error_count, question
        FROM user_wrong_questions
        WHERE user_id=?
        ORDER BY id DESC
        """,
        (user_id,),
    ).fetchall()
    existing = next(
        ((row_id, error_count) for row_id, error_count, question in candidates
         if _space_fold(question) == question_key),
        None,
    )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(user_wrong_questions)")}
    has_images_column = "images" in columns
    images_json = json.dumps(data["images"], ensure_ascii=False)
    if existing:
        row_id, old_error_count = existing
        update_values = (
            data["subject"], data["question"], data["myAnswer"],
            data["correctAnswer"], data["explanation"],
            max(old_error_count or 1, data["errorCount"]), now,
        )
        if has_images_column and data["images"]:
            conn.execute(
                """UPDATE user_wrong_questions
                   SET subject=?, question=?, user_answer=?, correct_answer=?, explanation=?,
                       error_count=?, status='active', created_at=?, images=?
                   WHERE id=? AND user_id=?""",
                update_values + (images_json, row_id, user_id),
            )
        else:
            conn.execute(
                """UPDATE user_wrong_questions
                   SET subject=?, question=?, user_answer=?, correct_answer=?, explanation=?,
                       error_count=?, status='active', created_at=?
                   WHERE id=? AND user_id=?""",
                update_values + (row_id, user_id),
            )
        conn.commit()
        return {"ok": True, "updated": True, "id": row_id}

    insert_values = (
        user_id, data["subject"], data["question"], data["myAnswer"],
        data["correctAnswer"], data["explanation"], data["errorCount"],
    )
    if has_images_column:
        cur = conn.execute(
            """INSERT INTO user_wrong_questions
                   (user_id, subject, question, user_answer, correct_answer,
                    explanation, error_count, status, images)
               VALUES (?,?,?,?,?,?,?,'active',?)""",
            insert_values + (images_json,),
        )
    else:
        cur = conn.execute(
            """INSERT INTO user_wrong_questions
                   (user_id, subject, question, user_answer, correct_answer, explanation, error_count, status)
               VALUES (?,?,?,?,?,?,?,'active')""",
            insert_values,
        )
    conn.commit()
    return {"ok": True, "inserted": True, "id": cur.lastrowid}
