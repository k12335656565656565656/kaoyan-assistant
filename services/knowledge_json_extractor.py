import json
import re

from schemas.knowledge_schema import (
    knowledge_point_to_dict,
    normalize_knowledge_point_drafts,
    validate_required_fields,
)


def build_knowledge_json_prompt(text: str, subject: str = "", chapter_name: str = "", max_points: int = 12) -> str:
    return f"""你是专业课知识点抽取助手。请只基于用户提供的资料内容提取知识点，不要编造资料中没有的事实。

任务要求：
1. 输出必须是合法 JSON 数组。
2. 不要输出 Markdown。
3. 不要输出 ```json。
4. 不要输出任何解释性文字。
5. 最多输出 {max_points} 个知识点对象。
6. 每个对象尽量包含以下字段：
   - knowledge_name
   - knowledge_type
   - subject
   - chapter_name
   - core_definition
   - exam_question_styles
   - keywords
   - related_concepts
   - pitfalls
   - example_or_application
   - review_priority
   - source_text
   - source_page
   - source_location
   - tags
   - mastery_state
   - is_ai_expansion
   - uncertainty_note
7. source_text 必须尽量引用原文片段作为依据。
8. 如果某字段无法从原文判断，可以留空，或写入 uncertainty_note。
9. 如果某项内容属于 AI 发散或补全，必须标记 is_ai_expansion=true。
10. exam_question_styles、keywords、related_concepts、pitfalls、tags 应尽量使用数组。

学科：{subject}
章节：{chapter_name}

资料原文：
{text}"""


def _strip_code_fences(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _extract_first_json_array(text: str) -> str:
    start = text.find("[")
    if start == -1:
        return ""

    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return ""


def parse_knowledge_points_json(raw_output: str, max_points: int = 12):
    warnings = []
    cleaned = _strip_code_fences(raw_output)
    payload = None

    parse_candidates = []
    if cleaned:
        parse_candidates.append(cleaned)
    first_array = _extract_first_json_array(cleaned)
    if first_array and first_array not in parse_candidates:
        parse_candidates.append(first_array)

    for candidate in parse_candidates:
        try:
            payload = json.loads(candidate)
            break
        except json.JSONDecodeError:
            continue

    if payload is None:
        warnings.append("模型返回的内容不是可解析的 JSON。")
        if cleaned:
            warnings.append(f"原始输出片段：{cleaned[:200]}")
        return [], warnings

    if isinstance(payload, dict):
        if isinstance(payload.get("knowledge_points"), list):
            payload = payload.get("knowledge_points")
        else:
            warnings.append("JSON 顶层不是数组，且未找到 knowledge_points 字段。")
            return [], warnings

    if not isinstance(payload, list):
        warnings.append("解析后的 JSON 不是数组。")
        return [], warnings

    normalized = normalize_knowledge_point_drafts(payload[:max_points])
    draft_dicts = [knowledge_point_to_dict(item) for item in normalized]

    for index, draft in enumerate(draft_dicts, start=1):
        for warning in validate_required_fields(draft):
            warnings.append(f"第{index}条：{warning}")

    return normalized, warnings


def extract_knowledge_points_as_drafts(
    text: str,
    subject: str = "",
    chapter_name: str = "",
    max_points: int = 12,
    llm_callable=None,
):
    warnings = []
    if llm_callable is None:
        return [], ["未提供 LLM 调用函数，无法执行知识点提取。"]

    safe_text = (text or "").strip()
    if not safe_text:
        return [], ["输入文本为空，无法提取知识点。"]

    max_chars = 3500
    if len(safe_text) > max_chars:
        safe_text = safe_text[:max_chars]
        warnings.append(f"当前仅处理前 {max_chars} 个字符，后续可在 PR5/PR6 继续增强长文本分段。")

    prompt = build_knowledge_json_prompt(safe_text, subject=subject, chapter_name=chapter_name, max_points=max_points)

    try:
        raw_output = llm_callable(prompt)
    except Exception as exc:
        warnings.append(f"调用模型失败：{exc}")
        return [], warnings

    drafts, parse_warnings = parse_knowledge_points_json(raw_output, max_points=max_points)
    warnings.extend(parse_warnings)
    return drafts, warnings
