from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable


LlmCallable = Callable[[str], str]
ProgressCallback = Callable[[int, int, str], None]


def _emit_progress(
    callback: ProgressCallback | None,
    current: int,
    total: int,
    message: str,
) -> None:
    if not callback:
        return
    try:
        callback(current, total, message)
    except Exception:
        return


def _extract_json_array(raw_output: str) -> list[Any]:
    text = str(raw_output or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        if start < 0:
            raise ValueError("模型没有返回 JSON 数组。")
        decoder = json.JSONDecoder()
        try:
            payload, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError as exc:
            raise ValueError("模型返回的 JSON 无法解析。") from exc
    if not isinstance(payload, list):
        raise ValueError("模型返回结果不是 JSON 数组。")
    return payload


def _clean_text(value: Any, limit: int = 0) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if limit and len(text) > limit:
        return text[:limit].rstrip("，。；; ")
    return text


def _clean_list(value: Any, *, limit: int = 8) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[；;、|\n]+", value)
    if not isinstance(value, (list, tuple, set)):
        return []
    cleaned: list[str] = []
    for item in value:
        text = _clean_text(item, 80)
        if text and text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _domain_instruction(subject: str) -> str:
    if "历史" in str(subject or ""):
        return (
            "这是历史类背诵材料。核心内容要交代必要的时间与背景、主要过程或制度内容、"
            "结果与影响、历史定位；人物、制度和事件不得混写。"
        )
    return (
        "核心内容要讲清定义、成立条件、关键过程、作用或影响；内容应适合闭卷背诵，"
        "不能只给标题换一种说法。"
    )


def build_syllabus_topic_index_prompt(
    syllabus_text: str,
    *,
    subject: str,
    max_points: int,
) -> str:
    return f"""你是考研专业课背诵目录编辑。请先通读整份考试大纲，把它拆成可独立背诵、可独立考查的知识条目。

只输出合法 JSON 数组，不要 Markdown、解释、前言或思考过程。最多输出 {max_points} 条。

每项格式：
{{"id":"k001","chapter_name":"所属科目或章节","knowledge_name":"具体背诵条目","source_anchor":"触发该条目的大纲原词"}}

要求：
1. 覆盖大纲中的所有主要部分，不能只处理前半部分。
2. 大章节不能直接充当知识点，要继续拆到事件、制度、人物、理论、机制或具体专题。
3. 同义项合并；不要加入大纲范围之外的专题。
4. chapter_name 必须便于形成手册目录，同一层级名称保持一致。
5. source_anchor 只写对应的大纲原词，控制在 80 字以内。
6. 不要把考试性质、分值、宣传语、年份标题当作背诵条目。

专业课：{subject}

考试大纲：
{str(syllabus_text or '').strip()[:50000]}"""


def _parse_topic_index(raw_output: str, *, max_points: int) -> list[dict]:
    payload = _extract_json_array(raw_output)
    topics: list[dict] = []
    seen: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    for index, item in enumerate(payload, start=1):
        if isinstance(item, str):
            item = {"knowledge_name": item}
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("knowledge_name") or item.get("title"), 100)
        chapter = _clean_text(item.get("chapter_name") or item.get("chapter"), 100)
        if len(title) < 2:
            continue
        identity = (chapter.lower(), title.lower())
        if identity in seen:
            continue
        seen.add(identity)
        topic_id = _clean_text(item.get("id"), 24) or f"k{index:03d}"
        if topic_id in seen_ids:
            topic_id = f"k{index:03d}"
        while topic_id in seen_ids:
            topic_id = f"{topic_id}_{len(seen_ids) + 1}"
        seen_ids.add(topic_id)
        topics.append(
            {
                "id": topic_id,
                "chapter_name": chapter or "大纲核心内容",
                "knowledge_name": title,
                "source_anchor": _clean_text(
                    item.get("source_anchor") or item.get("source_text") or title,
                    160,
                ),
            }
        )
        if len(topics) >= max_points:
            break
    if not topics:
        raise ValueError("大模型没有从大纲中整理出可用的背诵条目。")
    return topics


def build_syllabus_expansion_prompt(
    topics: list[dict],
    *,
    subject: str,
) -> str:
    topic_json = json.dumps(topics, ensure_ascii=False, separators=(",", ":"))
    return f"""你是考研专业课背诵讲义编写者。请把下面这批大纲条目写成考生可以直接背诵的内容。

只输出合法 JSON 数组，不要 Markdown、前言、来源编号、页码、思考过程或说明。必须逐条返回，id 不得改变。

每项字段：
- id
- core_definition：180-420 字，直接写知识内容，不说“根据大纲”“下面介绍”
- keywords：4-8 个关键词数组
- related_concepts：2-5 个关联知识数组
- exam_question_styles：2-4 个可能考法数组
- pitfalls：2-4 个易错点数组
- example_or_application：一段简洁的答题展开顺序或材料题应用
- review_priority：高、中、低之一

写作要求：
1. {_domain_instruction(subject)}
2. 内容必须完整到足以背诵，不能只重复标题。
3. 不虚构具体史料引文、学者观点、统计数字或学校偏好。
4. 遇到存在学术争议的内容，使用稳妥表述，不强行下唯一结论。
5. 语言像复习讲义，不使用“首先我们”“作为 AI”“建议咨询”等套话。

专业课：{subject}
待扩写条目：
{topic_json}"""


def _parse_expanded_batch(raw_output: str, topics: list[dict], subject: str) -> list[dict]:
    payload = _extract_json_array(raw_output)
    topic_by_id = {item["id"]: item for item in topics}
    topic_by_title = {item["knowledge_name"]: item for item in topics}
    expanded: list[dict] = []
    seen_ids: set[str] = set()

    for item in payload:
        if not isinstance(item, dict):
            continue
        topic_id = _clean_text(item.get("id"), 24)
        topic = topic_by_id.get(topic_id)
        if topic is None:
            topic = topic_by_title.get(_clean_text(item.get("knowledge_name"), 100))
        if topic is None or topic["id"] in seen_ids:
            continue
        core = _clean_text(item.get("core_definition") or item.get("content"), 1600)
        if len(core) < 60:
            continue
        seen_ids.add(topic["id"])
        expanded.append(
            {
                "knowledge_name": topic["knowledge_name"],
                "knowledge_type": "背诵知识点",
                "subject": subject,
                "chapter_name": topic["chapter_name"],
                "core_definition": core,
                "exam_question_styles": _clean_list(item.get("exam_question_styles"), limit=4),
                "keywords": _clean_list(item.get("keywords"), limit=8),
                "related_concepts": _clean_list(item.get("related_concepts"), limit=5),
                "pitfalls": _clean_list(item.get("pitfalls"), limit=4),
                "example_or_application": _clean_text(item.get("example_or_application"), 600),
                "review_priority": _clean_text(item.get("review_priority"), 4)
                if _clean_text(item.get("review_priority"), 4) in {"高", "中", "低"}
                else "中",
                "source_text": topic["source_anchor"],
                "source_location": topic["chapter_name"],
                "tags": [subject, topic["chapter_name"], "大纲背诵"],
                "mastery_state": "待复习",
                "is_ai_expansion": True,
                "uncertainty_note": "",
            }
        )
    return expanded


def generate_syllabus_memorization_points(
    syllabus_text: str,
    *,
    subject: str,
    llm_callable: LlmCallable,
    max_points: int = 60,
    batch_size: int = 5,
    max_workers: int = 3,
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[dict], list[str]]:
    safe_text = str(syllabus_text or "").strip()
    if not safe_text:
        raise ValueError("大纲中没有可读取的文字。")
    max_points = min(100, max(10, int(max_points or 60)))
    batch_size = min(8, max(2, int(batch_size or 5)))
    max_workers = min(4, max(1, int(max_workers or 1)))

    _emit_progress(progress_callback, 0, 2, "正在通读大纲并建立背诵目录")
    index_output = llm_callable(
        build_syllabus_topic_index_prompt(
            safe_text,
            subject=subject,
            max_points=max_points,
        )
    )
    topics = _parse_topic_index(index_output, max_points=max_points)
    batches = [topics[index : index + batch_size] for index in range(0, len(topics), batch_size)]
    total_steps = len(batches) + 1
    _emit_progress(progress_callback, 1, total_steps, f"已整理 {len(topics)} 个背诵条目，开始分批扩写")

    def expand_batch(batch: list[dict]) -> tuple[list[dict], list[str]]:
        prompt = build_syllabus_expansion_prompt(batch, subject=subject)
        raw_output = llm_callable(prompt)
        expanded = _parse_expanded_batch(raw_output, batch, subject)
        if len(expanded) < len(batch):
            missing = [
                item for item in batch
                if item["knowledge_name"] not in {point["knowledge_name"] for point in expanded}
            ]
            if missing:
                retry_output = llm_callable(build_syllabus_expansion_prompt(missing, subject=subject))
                expanded.extend(_parse_expanded_batch(retry_output, missing, subject))
        if len(expanded) < len(batch):
            missing_titles = [
                item["knowledge_name"] for item in batch
                if item["knowledge_name"] not in {point["knowledge_name"] for point in expanded}
            ]
            return expanded, ["以下条目未成功生成：" + "、".join(missing_titles)]
        return expanded, []

    completed_batches: dict[int, tuple[list[dict], list[str]]] = {}
    worker_count = min(max_workers, len(batches))
    if worker_count == 1:
        for batch_index, batch in enumerate(batches, start=1):
            _emit_progress(
                progress_callback,
                batch_index,
                total_steps,
                f"正在生成第 {batch_index}/{len(batches)} 批背诵内容",
            )
            completed_batches[batch_index] = expand_batch(batch)
    else:
        _emit_progress(
            progress_callback,
            1,
            total_steps,
            f"正在并行生成 {len(batches)} 批背诵内容",
        )
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(expand_batch, batch): batch_index
                for batch_index, batch in enumerate(batches, start=1)
            }
            for completed_count, future in enumerate(as_completed(futures), start=1):
                batch_index = futures[future]
                completed_batches[batch_index] = future.result()
                _emit_progress(
                    progress_callback,
                    completed_count + 1,
                    total_steps,
                    f"已完成 {completed_count}/{len(batches)} 批背诵内容",
                )

    points: list[dict] = []
    warnings: list[str] = []
    for batch_index in sorted(completed_batches):
        batch_points, batch_warnings = completed_batches[batch_index]
        points.extend(batch_points)
        warnings.extend(batch_warnings)

    minimum_count = max(1, round(len(topics) * 0.8))
    if len(points) < minimum_count:
        raise RuntimeError(
            f"大模型只成功生成 {len(points)}/{len(topics)} 个条目，未达到完整性要求，请重试。"
        )
    _emit_progress(progress_callback, total_steps, total_steps, f"已生成 {len(points)} 个背诵条目")
    return points, warnings
