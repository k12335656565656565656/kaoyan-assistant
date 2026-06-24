from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from services.llm_gateway import chat_completion_text, stream_chat_completion


@dataclass
class MathQaTurnResult:
    raw_full: str
    output: dict
    answer_text: str
    matched_knowledge: list[str]
    references: list[dict]


def search_corpus(query: str, corpus: list[dict], top_k: int = 3) -> list[dict]:
    if not corpus or not query:
        return []
    query_lower = query.lower()
    results = []
    for doc in corpus:
        text = doc["text"].lower()
        score = sum(text.count(token) for token in query_lower.split() if token)
        if score > 0:
            results.append({"id": doc["id"], "score": score, "text": doc["text"][:500]})
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:top_k]


def parse_multi_output(raw_text: str, latex_fix_fn: Callable[[str], str] | None = None) -> dict:
    """Parse one-shot [ANSWER]/[KNOWLEDGE] tagged model output."""
    latex_fix_fn = latex_fix_fn or (lambda value: value)
    if "[ANSWER]" not in raw_text:
        cleaned = (
            raw_text.replace("\\(", "$")
            .replace("\\)", "$")
            .replace("\\[", "$$")
            .replace("\\]", "$$")
        )
        return {"answer": cleaned[:2000], "knowledge": [], "quiz": ""}

    def extract(begin: str, end: str) -> str:
        if begin in raw_text and end in raw_text:
            return raw_text.split(begin, 1)[1].split(end, 1)[0].strip()
        return ""

    knowledge_part = raw_text.split("[KNOWLEDGE]", 1)[-1] if "[KNOWLEDGE]" in raw_text else ""
    knowledge_raw = knowledge_part.split("[", 1)[0].strip() if "[" in knowledge_part else knowledge_part.strip()
    return {
        "answer": latex_fix_fn(extract("[ANSWER]", "[KNOWLEDGE]") or raw_text[:1500]),
        "knowledge": [item.strip() for item in knowledge_raw.split(",") if item.strip()],
    }


def build_math_qa_system_prompt(*, context: str, skill_prompt: str = "") -> str:
    math_rules = r"""- 所有公式必须用 $...$ 包裹，例如 $f(x)$、$\int_{a}^{b}$、$\frac{a}{b}$
- 独立公式用 $$...$$，例如 $$\lim_{x \to 0} \frac{\sin x}{x} = 1$$
- 禁止使用 \( \) 或 \[ \]
- 禁止在 $ 外面写 \frac、\int、\lim、\pi 等 LaTeX 命令"""

    return f"""你是考研数学辅导专家。请完成以下任务并用标签输出：

任务1：根据参考资料回答用户问题。{"严格遵循 Skill 的格式要求。" if skill_prompt else ""}

任务2：判断问题涉及的知识点，输出概念名称（如：导数, 定积分, 矩阵）。

⚠️ 数学公式强制规则（必须遵守，否则无法显示）：
{math_rules}

输出格式：
[ANSWER]
（回答）

[KNOWLEDGE]
（概念名，逗号分隔）

{skill_prompt if skill_prompt else ""}

参考资料：
{context}"""


def stream_math_qa(
    *,
    query: str,
    results: list[dict],
    model_name: str,
    skill_prompt: str = "",
    img_data: str | None = None,
    latex_fix_fn: Callable[[str], str] | None = None,
) -> Iterable[dict]:
    context = "\n\n".join([f"【{doc['id']}】\n{doc['text'][:800]}" for doc in results[:3]]) if results else ""
    system_prompt = build_math_qa_system_prompt(context=context, skill_prompt=skill_prompt)
    if img_data:
        user_content = [
            {"type": "text", "text": f"问题：{query}"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_data}"}},
        ]
    else:
        user_content = f"问题：{query}"

    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}]
    max_tokens = 800 if img_data else 1500
    temperature = 0.3
    raw_full = ""

    try:
        for delta in stream_chat_completion(
            messages=messages,
            model=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=180,
        ):
            raw_full += delta
            yield {"type": "token", "content": delta}
    except Exception:
        raw_full = chat_completion_text(
            messages=messages,
            model=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=180,
        )
        yield {"type": "token", "content": raw_full}

    output = parse_multi_output(raw_full, latex_fix_fn=latex_fix_fn)
    output["_raw_debug"] = raw_full[:500]
    output["qtype"] = "math"
    output["pipeline_log"] = []
    yield {"type": "done", "result": output}


def extract_answer_text(output: dict | None, raw_full: str) -> str:
    if output and output.get("answer"):
        return str(output["answer"]).strip()
    if not raw_full:
        return ""
    if "[ANSWER]" in raw_full:
        answer_text = raw_full.split("[ANSWER]", 1)[1]
        if "[KNOWLEDGE]" in answer_text:
            answer_text = answer_text.split("[KNOWLEDGE]")[0]
        return answer_text.strip()
    return raw_full.strip()


def normalize_knowledge_hits(knowledge_items: list[str], matcher_fn: Callable[[str], list[str]]) -> list[str]:
    validated = []
    for item in knowledge_items or []:
        match = matcher_fn(item.strip())
        validated.append(match[0] if match else item.strip())
    return list(dict.fromkeys(validated))


def complete_math_qa_turn(
    *,
    query: str,
    output: dict,
    raw_full: str,
    results: list[dict],
    matcher_fn: Callable[[str], list[str]],
) -> MathQaTurnResult:
    answer_text = extract_answer_text(output, raw_full)
    matched_knowledge = normalize_knowledge_hits(output.get("knowledge") or [], matcher_fn)
    return MathQaTurnResult(
        raw_full=raw_full,
        output=output,
        answer_text=answer_text,
        matched_knowledge=matched_knowledge,
        references=results,
    )
