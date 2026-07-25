import re

from services.professional_question_prompts import is_408_knowledge_point


def is_placeholder_question(question):
    normalized = re.sub(r"[\s。！？!?,，:：；;、]+", "", str(question or "")).strip()
    return normalized in {"", "题目", "问题", "练习题", "概念自测", "请作答"}


def looks_like_408_exam_task(generated, mode, point=None):
    if point is not None and not is_408_knowledge_point(point):
        return True
    question = str(generated.get("question") or "")
    options = " ".join(str(item) for item in (generated.get("options") or []))
    body = f"{question} {options}".lower()
    bad_markers = (
        "只需要背定义",
        "所有相关题目",
        "任何题都可以直接套固定公式",
        "不需要说明过程",
        "围绕“",
        "某同学把它和相邻概念混用",
        "给出一个围绕",
    )
    if any(marker.lower() in body for marker in bad_markers):
        return False
    concrete_patterns = [
        r"\d",
        r"[a-z]\s*->\s*[a-z]",
        r"[{}\[\]()]",
        r"\b0x[0-9a-f]+\b",
        r"[0-9a-f]{4,}h\b",
        r"ip|tcp|udp|ack|crc|cache|tlb|fifo|lru|clock|dma|alu|wpl|aov|kmp|b\+?树|dijkstra|floyd|dist",
        r"边集|序列|页框|页面访问串|资源矩阵|路由表|地址字段|主存地址|指令格式|入度|前驱|后继|先序|中序|后序|频率|权值|窗口|子网|掩码|流水线|信号量|进程|无穷大|最短路径|松弛|距离数组|候选集|顶点集",
    ]
    concrete_hits = sum(1 for pattern in concrete_patterns if re.search(pattern, body, re.IGNORECASE))
    task_verbs = (
        "计算", "判断", "写出", "画出", "构造", "推导", "说明", "比较", "分析", "设计", "给出",
        "填空", "补全", "选出", "选择", "正确", "错误", "最合适", "符合", "不符合",
        "确定", "求", "求出", "填写", "更新", "松弛", "改用",
    )
    verb_hits = sum(1 for verb in task_verbs if verb in question)
    if mode == "choice":
        return concrete_hits >= 1 and len(generated.get("options") or []) >= 4
    if mode in {"concept", "blank"}:
        return concrete_hits >= 1 and verb_hits >= 1
    return concrete_hits >= 2 and verb_hits >= 2


def choice_reference_has_conflict(generated):
    correct = str(generated.get("correct_answer") or "").strip().upper()[:1]
    if correct not in {"A", "B", "C", "D"}:
        return True
    reference = str(generated.get("reference_answer") or "")
    shaky_markers = (
        "与选项不符",
        "可能指另一种",
        "题目描述的",
        "但此过程",
        "无法确定",
        "存在歧义",
        "口径不一致",
    )
    if any(marker in reference for marker in shaky_markers):
        return True
    for label in ("A", "B", "C", "D"):
        if label == correct:
            continue
        option_claims_correct = re.search(
            rf"(?:选项)?{label}[^。；;\n]{{0,45}}(?:正确|可行|符合|成立)",
            reference,
        )
        if option_claims_correct:
            return True
    return False


def reference_has_internal_conflict(generated):
    body = "\n".join(
        str(generated.get(field) or "")
        for field in ("question", "correct_answer", "reference_answer")
    )
    conflict_markers = (
        "但答案给出",
        "答案给出",
        "严格来说",
        "可能是基于",
        "可能假设",
        "存在歧义",
        "无法确定答案",
        "无法确定正确答案",
        "不一致",
        "互相矛盾",
        "这可能是",
        "为了符合题目要求",
    )
    return any(marker in body for marker in conflict_markers)


def blank_marker_count(question):
    body = str(question or "")
    patterns = (
        r"_{3,}",
        r"（\s*）",
        r"\(\s*\)",
        r"【\s*】",
        r"\[\s*\]",
        r"空\s*\d+",
    )
    return sum(len(re.findall(pattern, body)) for pattern in patterns)


def split_blank_answers(answer_text):
    text = str(answer_text or "")
    if "；" in text or ";" in text or "\n" in text:
        separators = r"[；;\n]+"
    elif "，" in text:
        separators = r"[，]+"
    elif "," in text and not re.search(r"[\[\]()]|min\s*\(", text, re.IGNORECASE):
        separators = r"[,]+"
    else:
        separators = r"$^"
    return [
        item.strip(" \t\r\n'\"[]()（）")
        for item in re.split(separators, text)
        if item.strip(" \t\r\n'\"[]()（）")
    ]


def normalize_answer_for_match(text):
    return re.sub(r"\s+", "", str(text or "")).lower()


def reference_asserts_blank_answer(reference, answer):
    normalized_reference = normalize_answer_for_match(reference)
    normalized_answer = normalize_answer_for_match(answer)
    if not normalized_answer:
        return False
    if normalized_answer not in normalized_reference:
        formula_markers = ("min(", "max(", "dist[", "d[", "w(")
        if any(marker in normalized_answer for marker in formula_markers):
            formula_overlap = sum(
                1 for marker in formula_markers
                if marker in normalized_answer and marker in normalized_reference
            )
            has_assignment = "=" in normalized_answer and "=" in normalized_reference
            if formula_overlap >= 2 and has_assignment:
                return True
        return False

    is_single_choice_like = bool(re.fullmatch(r"[a-d]", normalized_answer, re.IGNORECASE))
    is_short_number = bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?", normalized_answer))
    is_short_symbol = normalized_answer in {"∞", "无穷大"}
    if not (is_single_choice_like or is_short_number or is_short_symbol):
        return True

    conclusion_markers = (
        "填",
        "填写",
        "应填",
        "故填",
        "空为",
        "答案为",
        "结果为",
        "长度为",
        "距离为",
        "值为",
        "等于",
        "是",
    )
    for marker in conclusion_markers:
        start = 0
        while True:
            index = normalized_reference.find(marker, start)
            if index < 0:
                break
            segment = normalized_reference[index + len(marker):index + len(marker) + 18]
            answer_index = segment.find(normalized_answer)
            if answer_index >= 0:
                prefix = segment[:answer_index]
                if is_short_number and re.search(r"\d", prefix):
                    start = index + len(marker)
                    continue
                return True
            start = index + len(marker)

    if is_single_choice_like:
        return False
    return normalized_reference.count(normalized_answer) >= 2


def blank_answers_are_supported_by_reference(generated):
    answers = split_blank_answers(generated.get("correct_answer"))
    if not answers:
        return False
    question = str(generated.get("question") or "")
    reference = str(generated.get("reference_answer") or "")
    blank_count = blank_marker_count(question)
    if blank_count > 1 and len(answers) < blank_count:
        return False
    for answer in answers:
        if not reference_asserts_blank_answer(reference, answer):
            return False
    return True


def is_valid_professional_question_for_point(generated, mode, point=None):
    question = str(generated.get("question") or "").strip()
    reference_answer = str(generated.get("reference_answer") or "").strip()
    if is_placeholder_question(question) or len(question) < 18 or not reference_answer:
        return False
    if reference_has_internal_conflict(generated):
        return False
    if mode == "choice":
        options = generated.get("options") or []
        if len(options) < 4 or not str(generated.get("correct_answer") or "").strip():
            return False
        if choice_reference_has_conflict(generated):
            return False
    if mode == "blank":
        if blank_marker_count(question) < 1:
            return False
        if not str(generated.get("correct_answer") or "").strip():
            return False
        if not blank_answers_are_supported_by_reference(generated):
            return False
    if point is not None and is_408_knowledge_point(point):
        if not looks_like_408_exam_task(generated, mode, point=point):
            return False
    return True


def is_valid_professional_question(generated, mode):
    return is_valid_professional_question_for_point(generated, mode, None)
