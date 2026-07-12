import json
import math
import re
from typing import Callable

from schemas.knowledge_schema import (
    knowledge_point_to_dict,
    normalize_knowledge_point_draft,
    normalize_knowledge_point_drafts,
    validate_required_fields,
)


def build_knowledge_json_prompt(
    text: str,
    subject: str = "",
    chapter_name: str = "",
    max_points: int = 12,
    extraction_guidance: str = "",
) -> str:
    guidance = (extraction_guidance or "").strip()
    guidance_block = (
        f"\n学科补充抽取规则（只用于强调重点，不能突破原文依据）：\n{guidance}\n"
        if guidance
        else ""
    )
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
8. source_page 必须尽量从资料中的“=== 第N页 ===”标记中提取；无法判断时留空并写 uncertainty_note。
9. source_location 必须尽量填写题号、段落或小节，例如“题5”“题16”“数据结构题6”。
10. 只提取可复习、可考察、可归纳的专业概念、原理、算法、结构、协议、机制、公式、模型或典型考法。
11. 不要把页眉、页脚、目录项、参考文献、作者单位、普通过渡句、例题编号、纯说明性废话当成知识点。
12. 如果某字段无法从原文判断，可以留空，或写入 uncertainty_note。
13. 如果某项内容属于 AI 发散或补全，必须标记 is_ai_expansion=true。
14. exam_question_styles、keywords、related_concepts、pitfalls、tags 应尽量使用数组。
15. 为避免 JSON 过长，摘要类字段尽量控制在 160 字以内，source_text 尽量保留完整题干、定义句或上下文证据，建议 80-300 字。
16. 不要输出代码大段、整段解析、长公式推导；只输出可复习的结构化摘要。

学科：{subject}
章节：{chapter_name}
{guidance_block}

资料原文：
{text}"""


def _strip_code_fences(text: str) -> str:
    cleaned = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _extract_first_json_array(text: str) -> str:
    start = text.find("[")
    if start == -1:
        return ""

    depth = 0
    in_string = False
    escape_next = False
    for index in range(start, len(text)):
        char = text[index]
        if escape_next:
            escape_next = False
            continue
        if char == "\\" and in_string:
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return ""


def _parse_complete_json_objects(text: str) -> list[dict]:
    """Best-effort recovery when the model starts an array but truncates before closing it."""
    objects = []
    start = -1
    depth = 0
    in_string = False
    escape_next = False

    for index, char in enumerate(text or ""):
        if escape_next:
            escape_next = False
            continue
        if char == "\\" and in_string:
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                fragment = text[start:index + 1]
                try:
                    payload = json.loads(fragment)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict):
                    objects.append(payload)
                start = -1
    return objects


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
        recovered_objects = _parse_complete_json_objects(cleaned)
        if recovered_objects:
            payload = recovered_objects
            warnings.append("模型返回的 JSON 不完整，已尽力恢复其中完整的知识点对象。")
        else:
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


_PAGE_MARKER_PATTERN = re.compile(r"===\s*第\s*(\d+)\s*页\s*===")
_QUESTION_SPLIT_PATTERN = re.compile(r"\n\s*(?=(?:题\s*)?\d+\s*[.．、:：])")


def _strip_noise_lines(text: str) -> str:
    noise_tokens = (
        "聚创考研",
        "juchuang",
        "找研讯",
        "找真题",
        "找辅导",
        "考研网",
        "扫描二维码",
        "微信公众号",
    )
    lines = []
    for line in re.split(r"\n+", text or ""):
        stripped = line.strip()
        if not stripped:
            continue
        if any(token.lower() in stripped.lower() for token in noise_tokens):
            continue
        if re.fullmatch(r"[-—_\s\d/]+", stripped):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _iter_page_sections(text: str):
    current_page = ""
    chunks = _PAGE_MARKER_PATTERN.split(text or "")
    if len(chunks) == 1:
        yield "", text or ""
        return

    prefix = chunks[0]
    if prefix.strip():
        yield "", prefix

    for index in range(1, len(chunks), 2):
        current_page = chunks[index].strip()
        content = chunks[index + 1] if index + 1 < len(chunks) else ""
        yield current_page, content


def _split_source_blocks_with_pages(text: str, max_points: int) -> list[tuple[str, str]]:
    cleaned = re.sub(r"\r\n?", "\n", text or "").strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    if not cleaned:
        return []

    blocks = []
    for page, section in _iter_page_sections(cleaned):
        section = _strip_noise_lines(section)
        if not section.strip():
            continue
        raw_blocks = [
            block.strip()
            for block in re.split(r"\n\s*\n|(?=\n?\s*\d+[.、]\s*)", section)
            if block.strip()
        ]
        if len(raw_blocks) < 2:
            raw_blocks = [block.strip() for block in re.split(r"(?<=[。！？；;])\s*", section) if block.strip()]

        buffer = ""
        for block in raw_blocks:
            compact = re.sub(r"\s+", " ", block).strip()
            if not compact:
                continue
            if len(compact) < 28 and not _looks_like_meaningful_short_block(compact):
                continue
            if len(compact) < 45 and buffer:
                buffer = f"{buffer} {compact}".strip()
                continue
            if buffer:
                blocks.append((buffer, page))
            buffer = compact
            if len(blocks) >= max_points:
                return blocks[:max_points]
        if buffer and len(blocks) < max_points:
            blocks.append((buffer, page))

    return blocks[:max_points]


def _split_text_for_llm(text: str, target_chars: int = 2400, hard_limit: int = 3200) -> list[str]:
    cleaned = re.sub(r"\r\n?", "\n", text or "").strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    if not cleaned:
        return []

    page_pieces = []
    for page, section in _iter_page_sections(cleaned):
        for piece in _split_page_section(page, section, hard_limit=hard_limit):
            if piece.strip():
                page_pieces.append(piece.strip())

    if not page_pieces:
        return [cleaned[:hard_limit]]

    chunks = []
    current = ""
    for piece in page_pieces:
        if not current:
            current = piece
            continue
        candidate = f"{current}\n\n{piece}"
        if len(candidate) <= hard_limit:
            current = candidate
            continue
        chunks.append(current)
        current = piece

    if current:
        chunks.append(current)

    merged = []
    buffer = ""
    for chunk in chunks:
        if not buffer:
            buffer = chunk
            continue
        candidate = f"{buffer}\n\n{chunk}"
        if len(buffer) < target_chars and len(candidate) <= hard_limit:
            buffer = candidate
            continue
        merged.append(buffer)
        buffer = chunk
    if buffer:
        merged.append(buffer)

    return merged or [cleaned[:hard_limit]]


def _select_chunks_for_point_budget(chunks: list[str], max_points: int) -> list[tuple[int, str]]:
    """Select source chunks evenly when the point budget cannot cover every chunk."""
    if not chunks or max_points <= 0:
        return []

    selection_count = min(len(chunks), max_points)
    if selection_count == len(chunks):
        return list(enumerate(chunks, start=1))
    if selection_count == 1:
        return [(1, chunks[0])]

    last_index = len(chunks) - 1
    selected_indexes = [
        round(position * last_index / (selection_count - 1))
        for position in range(selection_count)
    ]
    return [(index + 1, chunks[index]) for index in selected_indexes]


def _split_page_section(page: str, section: str, hard_limit: int) -> list[str]:
    section = (section or "").strip()
    if not section:
        return []

    marker = f"=== 第{page}页 ===\n" if page else ""
    whole = f"{marker}{section}".strip()
    if len(whole) <= hard_limit:
        return [whole]

    raw_blocks = [
        block.strip()
        for block in re.split(r"\n\s*\n|" + _QUESTION_SPLIT_PATTERN.pattern, section)
        if block.strip()
    ]
    if len(raw_blocks) < 2:
        raw_blocks = [block.strip() for block in re.split(r"(?<=[。！？；;])\s*", section) if block.strip()]
    if len(raw_blocks) < 2:
        return [whole[:hard_limit]]

    pieces = []
    current_body = ""
    for block in raw_blocks:
        block = block.strip()
        if not block:
            continue
        candidate_body = f"{current_body}\n{block}".strip() if current_body else block
        candidate_text = f"{marker}{candidate_body}".strip()
        if current_body and len(candidate_text) > hard_limit:
            pieces.append(f"{marker}{current_body}".strip())
            current_body = block
            if len(f"{marker}{current_body}".strip()) > hard_limit:
                pieces.extend(_split_oversized_block(page, block, hard_limit))
                current_body = ""
        else:
            current_body = candidate_body

    if current_body:
        pieces.append(f"{marker}{current_body}".strip())

    return pieces


def _split_oversized_block(page: str, block: str, hard_limit: int) -> list[str]:
    marker = f"=== 第{page}页 ===\n" if page else ""
    parts = []
    sentences = [item.strip() for item in re.split(r"(?<=[。！？；;])\s*", block or "") if item.strip()]
    if len(sentences) < 2:
        sentences = [block[i:i + max(hard_limit - len(marker), 200)] for i in range(0, len(block), max(hard_limit - len(marker), 200))]

    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(f"{marker}{candidate}".strip()) > hard_limit:
            parts.append(f"{marker}{current}".strip())
            current = sentence
        else:
            current = candidate
    if current:
        parts.append(f"{marker}{current}".strip())
    return parts


def _split_source_blocks(text: str, max_points: int) -> list[str]:
    return [block for block, _page in _split_source_blocks_with_pages(text, max_points)]


def _looks_like_meaningful_short_block(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return False
    return compact.startswith(("题", "Q", "问")) or any(
        token in compact for token in ("是", "作用", "特点", "定义", "原理", "算法", "机制")
    )


def _infer_knowledge_name(block: str, index: int) -> str:
    text = re.sub(r"^\s*(\[\d+\]|\d+[.、]|第[一二三四五六七八九十]+[章节])\s*", "", block).strip()
    first_line = text.split("\n", 1)[0].strip()
    first_sentence = re.split(r"[。！？；;:：]", first_line, maxsplit=1)[0].strip()

    if 4 <= len(first_sentence) <= 28:
        return first_sentence
    if "是指" in text:
        candidate = text.split("是指", 1)[0].strip()
        if 2 <= len(candidate) <= 28:
            return candidate
    if "包括" in text:
        candidate = text.split("包括", 1)[0].strip()
        if 2 <= len(candidate) <= 28:
            return candidate
    return f"候选知识点{index}"


def _infer_keywords(block: str, name: str) -> list[str]:
    keywords = []
    for item in re.findall(r"[A-Za-z][A-Za-z0-9_+\-./]{2,}", block):
        if item not in keywords:
            keywords.append(item)
    for item in re.findall(r"[\u4e00-\u9fff]{2,8}", block):
        if item not in keywords and item not in name:
            keywords.append(item)
        if len(keywords) >= 8:
            break
    if name and name not in keywords:
        keywords.insert(0, name)
    return keywords[:8]


def _infer_knowledge_type(block: str) -> str:
    if any(token in block for token in ("方法", "步骤", "流程", "算法", "模型", "网络")):
        return "方法/模型"
    if any(token in block for token in ("定义", "概念", "是指")):
        return "概念"
    if any(token in block for token in ("作用", "意义", "用于", "功能")):
        return "作用/应用"
    return "知识点"


def _build_fallback_drafts(text: str, subject: str = "", chapter_name: str = "", max_points: int = 12):
    drafts = []
    for index, (block, page) in enumerate(_split_source_blocks_with_pages(text, max_points), start=1):
        name = _infer_knowledge_name(block, index)
        payload = {
            "knowledge_name": name,
            "knowledge_type": _infer_knowledge_type(block),
            "subject": subject,
            "chapter_name": chapter_name,
            "core_definition": block[:800],
            "exam_question_styles": ["名词解释", "简答题", "材料分析题"],
            "keywords": _infer_keywords(block, name),
            "related_concepts": [],
            "pitfalls": [],
            "example_or_application": "",
            "review_priority": "中",
            "source_text": block[:1200],
            "source_page": f"第{page}页" if page else "",
            "source_location": "本地兜底抽取",
            "tags": [subject, chapter_name, "本地兜底抽取"],
            "mastery_state": "待复习",
            "is_ai_expansion": False,
            "uncertainty_note": "模型调用失败或返回不可解析内容，本条由本地规则基于原文生成，请人工核对。",
        }
        drafts.append(normalize_knowledge_point_draft(payload))
    return drafts


def _dedupe_drafts(drafts: list) -> list:
    deduped = []
    seen = set()
    for draft in drafts:
        payload = knowledge_point_to_dict(draft)
        identity = (
            (payload.get("knowledge_name") or "").strip().lower(),
            (payload.get("source_page") or "").strip(),
            (payload.get("source_location") or "").strip(),
            re.sub(r"\s+", " ", payload.get("source_text") or "").strip()[:80],
        )
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(draft)
    return deduped


def _emit_progress(
    progress_callback: Callable[[int, int, str], None] | None,
    current: int,
    total: int,
    message: str,
) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(current, total, message)
    except Exception:
        return


def extract_knowledge_points_as_drafts(
    text: str,
    subject: str = "",
    chapter_name: str = "",
    max_points: int = 12,
    llm_callable=None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    extraction_guidance: str = "",
):
    warnings = []
    if llm_callable is None:
        return [], ["未提供 LLM 调用函数，无法执行知识点提取。"]

    safe_text = (text or "").strip()
    if not safe_text:
        return [], ["输入文本为空，无法提取知识点。"]

    _emit_progress(progress_callback, 0, 1, "正在整理待抽取文本...")
    chunks = _split_text_for_llm(safe_text)
    selected_chunks = _select_chunks_for_point_budget(chunks, max_points)
    sampled_chunks = len(selected_chunks) < len(chunks)
    if sampled_chunks:
        skipped_count = len(chunks) - len(selected_chunks)
        selected_positions = "、".join(str(source_index) for source_index, _chunk in selected_chunks)
        if len(selected_chunks) >= 3:
            coverage_description = "覆盖首段、中段和末段"
        elif len(selected_chunks) == 2:
            coverage_description = "覆盖首段和末段"
        else:
            coverage_description = "仅覆盖首段"
        warnings.append(
            f"资料较长，共切分为 {len(chunks)} 个片段；受最多 {max_points} 条知识点限制，"
            f"本次按全篇位置均匀选取 {len(selected_chunks)} 个片段抽取（原文第 {selected_positions} 段），"
            f"{coverage_description}。"
            f"其余 {skipped_count} 个片段本次未逐段调用模型。"
        )
    elif len(chunks) > 1:
        warnings.append(f"资料较长，已按 {len(chunks)} 个片段分段抽取，避免后页内容被截断。")

    total_steps = max(3, len(selected_chunks) * 3 + 2)
    current_step = 1
    if sampled_chunks:
        chunk_message = f"已从全篇 {len(chunks)} 个片段中均匀选取 {len(selected_chunks)} 个抽取片段"
    else:
        chunk_message = f"已整理为 {len(chunks)} 个抽取片段" if len(chunks) > 1 else "已整理抽取文本，准备开始归纳"
    _emit_progress(progress_callback, current_step, total_steps, chunk_message)

    all_drafts = []
    used_fallback = False
    for index, (source_chunk_index, chunk) in enumerate(selected_chunks, start=1):
        if len(all_drafts) >= max_points:
            break

        remaining = max_points - len(all_drafts)
        chunks_left = len(selected_chunks) - index + 1
        chunk_points = max(1, math.ceil(remaining / max(chunks_left, 1)))
        chunk_label = (
            f"选中片段 {index}/{len(selected_chunks)}（原文第 {source_chunk_index}/{len(chunks)} 段）"
            if sampled_chunks
            else f"第 {index}/{len(selected_chunks)} 段"
        )
        warning_label = f"原文第 {source_chunk_index} 段" if sampled_chunks else f"第 {index} 段"
        current_step += 1
        _emit_progress(
            progress_callback,
            current_step,
            total_steps,
            f"正在准备{chunk_label}，目标抽取 {min(chunk_points, remaining)} 条候选知识点",
        )
        prompt = build_knowledge_json_prompt(
            chunk,
            subject=subject,
            chapter_name=chapter_name,
            max_points=min(chunk_points, remaining),
            extraction_guidance=extraction_guidance,
        )

        try:
            current_step += 1
            _emit_progress(
                progress_callback,
                current_step,
                total_steps,
                f"正在抽取{chunk_label}候选知识点...",
            )
            raw_output = llm_callable(prompt)
        except Exception as exc:
            warnings.append(f"{warning_label}调用模型失败：{exc}")
            fallback_drafts = _build_fallback_drafts(
                chunk,
                subject=subject,
                chapter_name=chapter_name,
                max_points=min(chunk_points, remaining),
            )
            used_fallback = used_fallback or bool(fallback_drafts)
            all_drafts.extend(fallback_drafts)
            current_step += 1
            fallback_count = len(fallback_drafts)
            _emit_progress(
                progress_callback,
                current_step,
                total_steps,
                f"{chunk_label}模型失败，已切换本地兜底并生成 {fallback_count} 条草稿",
            )
            continue

        drafts, parse_warnings = parse_knowledge_points_json(raw_output, max_points=min(chunk_points, remaining))
        warnings.extend([f"{warning_label}：{warning}" for warning in parse_warnings])

        if not drafts:
            fallback_drafts = _build_fallback_drafts(
                chunk,
                subject=subject,
                chapter_name=chapter_name,
                max_points=min(chunk_points, remaining),
            )
            if fallback_drafts:
                warnings.append(f"{warning_label}模型输出无法解析，已启用本地兜底抽取。")
                used_fallback = True
            all_drafts.extend(fallback_drafts)
            current_step += 1
            _emit_progress(
                progress_callback,
                current_step,
                total_steps,
                f"{chunk_label}已用本地规则补齐，当前累计 {len(all_drafts)} 条草稿",
            )
            continue

        all_drafts.extend(drafts)
        current_step += 1
        _emit_progress(
            progress_callback,
            current_step,
            total_steps,
            f"{chunk_label}完成，当前累计 {len(all_drafts)} 条候选知识点",
        )

    current_step += 1
    _emit_progress(progress_callback, current_step, total_steps, "正在去重并整理候选知识点...")
    deduped = _dedupe_drafts(all_drafts)[:max_points]
    if not deduped and chunks:
        fallback_drafts = _build_fallback_drafts(
            safe_text,
            subject=subject,
            chapter_name=chapter_name,
            max_points=max_points,
        )
        if fallback_drafts:
            warnings.append("所有片段均未成功返回可用结果，已启用本地兜底抽取，生成的草稿需要人工核对后再保存。")
        _emit_progress(progress_callback, total_steps, total_steps, f"抽取完成，已生成 {len(fallback_drafts)} 条候选知识点")
        return fallback_drafts, warnings

    if used_fallback:
        warnings.append("已启用本地兜底抽取，生成的草稿需要人工核对后再保存。")

    _emit_progress(progress_callback, total_steps, total_steps, f"抽取完成，已整理出 {len(deduped)} 条候选知识点")
    return deduped, warnings
