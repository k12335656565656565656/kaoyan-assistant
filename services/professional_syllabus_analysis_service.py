from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import defaultdict
from typing import Any

from professional_knowledge.builtin_408 import ensure_builtin_408_points
from repositories.knowledge_repo import list_user_knowledge_points
from repositories.material_repo import ensure_material_schema
from repositories.professional_syllabus_repo import (
    get_syllabus_analysis,
    mark_syllabus_analysis_failed,
    mark_syllabus_analysis_running,
    save_syllabus_analysis_result,
)
from services.llm_gateway import simple_prompt_completion


SUBJECT_ORDER = {
    "数据结构": 1,
    "计算机组成原理": 2,
    "计组": 2,
    "操作系统": 3,
    "计算机网络": 4,
    "计网": 4,
}


def _parse_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _source_rows(conn: sqlite3.Connection, user_id: int, subject: str, source_ids: list[int]) -> list[dict]:
    ensure_material_schema(conn)
    normalized_ids = sorted({int(item) for item in source_ids if str(item).strip()})
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"""SELECT id, filename, chapter_name, confirmed_text, extracted_text, raw_extracted_text
            FROM user_materials
            WHERE user_id=? AND subject=? AND id IN ({placeholders})
            ORDER BY id DESC""",
        (user_id, subject, *normalized_ids),
    ).fetchall()
    return [dict(row) for row in rows]


def _source_text(rows: list[dict]) -> str:
    parts = []
    for row in rows:
        text = row.get("confirmed_text") or row.get("extracted_text") or row.get("raw_extracted_text") or ""
        if text:
            parts.append(f"【{row.get('chapter_name') or row.get('filename') or '资料'}】\n{text}")
    return "\n\n".join(parts)


def _point_subject(point: dict) -> str:
    return str(point.get("chapter_name") or point.get("source_location") or point.get("subject") or "未分类").strip()


def _point_terms(point: dict) -> list[str]:
    name = str(point.get("knowledge_name") or "")
    terms = [name]
    terms.extend(
        part.strip()
        for part in re.split(r"[与和及、：:（）()，,/\s]+", name)
        if len(part.strip()) >= 2
    )
    terms.extend(_parse_json_list(point.get("keywords_json")))
    terms.extend(_parse_json_list(point.get("related_concepts_json")))
    terms.extend(_parse_json_list(point.get("exam_question_styles_json")))
    clean_terms = []
    for term in terms:
        term = str(term or "").strip()
        if len(term) >= 2 and term not in clean_terms:
            clean_terms.append(term)
    return clean_terms


def _score_point(point: dict, compact_text: str) -> tuple[int, list[str]]:
    matched = []
    score = 0
    name = str(point.get("knowledge_name") or "").strip()
    if name and _compact(name) in compact_text:
        score += 12
        matched.append(name)
    for term in _point_terms(point):
        compact_term = _compact(term)
        if not compact_term or compact_term not in compact_text:
            continue
        weight = 5 if term == name else 3
        count = min(3, compact_text.count(compact_term))
        score += weight * count
        if term not in matched:
            matched.append(term)
    priority = str(point.get("review_priority") or "")
    if priority == "高":
        score += 1
    return score, matched[:5]


def _rank_points(points: list[dict], syllabus_text: str) -> list[dict]:
    compact_text = _compact(syllabus_text)
    ranked = []
    for point in points:
        score, matched = _score_point(point, compact_text)
        if score <= 0:
            continue
        ranked.append(
            {
                "knowledge_id": point.get("id"),
                "knowledge_name": point.get("knowledge_name") or "未命名知识点",
                "exam_subject": _point_subject(point),
                "score": score,
                "matched_terms": matched,
                "reason": f"考纲中出现：{'、'.join(matched)}" if matched else "与考纲主题相关",
                "review_priority": point.get("review_priority") or "中",
            }
        )
    ranked.sort(
        key=lambda item: (
            item["score"],
            -SUBJECT_ORDER.get(item["exam_subject"], 99),
        ),
        reverse=True,
    )
    return ranked


def _fallback_priority_points(points: list[dict], limit: int = 16) -> list[dict]:
    selected = []
    for point in points:
        if str(point.get("review_priority") or "") != "高":
            continue
        selected.append(
            {
                "knowledge_id": point.get("id"),
                "knowledge_name": point.get("knowledge_name") or "未命名知识点",
                "exam_subject": _point_subject(point),
                "score": 1,
                "matched_terms": [],
                "reason": "考纲文字未能精确匹配，先按 408 高频基础点纳入。",
                "review_priority": "高",
            }
        )
        if len(selected) >= limit:
            break
    return selected


def _build_school_focus(ranked: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for item in ranked[:36]:
        buckets[item["exam_subject"]].append(item)
    focus = []
    for subject, items in sorted(buckets.items(), key=lambda pair: SUBJECT_ORDER.get(pair[0], 99)):
        top_names = [item["knowledge_name"] for item in items[:5]]
        intensity = "高" if len(items) >= 8 or sum(item["score"] for item in items[:5]) >= 45 else "中"
        focus.append(
            {
                "exam_subject": subject,
                "intensity": intensity,
                "summary": f"这部分在资料中命中较多，优先看 {'、'.join(top_names[:3])}。",
                "evidence": top_names,
            }
        )
    return focus


def _build_phase_plan(priority_points: list[dict]) -> list[dict]:
    top_names = [item["knowledge_name"] for item in priority_points]
    return [
        {
            "phase": "基础阶段",
            "goal": "先把四大科目的核心概念和基本算法讲清楚。",
            "tasks": top_names[:8],
            "output": "每个知识点能说出核心定义、适用条件和一个易错点。",
        },
        {
            "phase": "强化阶段",
            "goal": "围绕学校高频方向做题，补齐过程推演和综合题表达。",
            "tasks": top_names[8:18] or top_names[:8],
            "output": "选择题能判断陷阱，综合题能按评分点分步作答。",
        },
        {
            "phase": "冲刺阶段",
            "goal": "回看错题和保存题，优先处理反复扣分的知识点。",
            "tasks": ["复练保存题", "整理错因", "按掌握度低的知识点回炉"],
            "output": "每个高频点至少完成 2 次复练，薄弱点进入记忆系统。",
        },
    ]


def _parse_llm_json(raw: str) -> dict:
    text = str(raw or "").strip()
    candidates = [text]
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        candidates.insert(0, match.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        return payload if isinstance(payload, dict) else {}
    return {}


def _llm_refine_analysis(
    *,
    subject: str,
    source_text: str,
    school_focus: list[dict],
    priority_points: list[dict],
    phase_plan: list[dict],
) -> tuple[list[dict], list[dict], list[dict], str]:
    if not os.environ.get("AI_API_KEY", "").strip():
        return school_focus, priority_points, phase_plan, ""
    prompt = f"""你是考研408专业课规划老师。请基于“用户上传的学校考纲/资料”和“系统已匹配出的408知识点”，润色成一份可执行学习画像。

要求：
1. 不编造学校名称、年份、真题。
2. 只围绕给定资料和匹配知识点说话。
3. 输出一行 JSON，字段固定：
{{"school_focus":[{{"exam_subject":"数据结构","intensity":"高|中|低","summary":"重点判断","evidence":["依据1"]}}],
"priority_points":[{{"knowledge_name":"知识点","exam_subject":"科目","priority":"高|中","reason":"为什么优先"}}],
"phase_plan":[{{"phase":"基础阶段","goal":"目标","tasks":["任务"],"output":"阶段产出"}}],
"raw_summary":"100字以内总评"}}

专业课：{subject}

用户资料节选：
{source_text[:9000]}

本地匹配结果：
学校重点：{json.dumps(school_focus, ensure_ascii=False)}
优先知识点：{json.dumps(priority_points[:24], ensure_ascii=False)}
阶段计划：{json.dumps(phase_plan, ensure_ascii=False)}
"""
    try:
        payload = _parse_llm_json(
            simple_prompt_completion(prompt, max_tokens=2200, temperature=0.2, timeout=120, retries=1)
        )
    except Exception:
        return school_focus, priority_points, phase_plan, ""
    refined_focus = payload.get("school_focus") if isinstance(payload.get("school_focus"), list) else school_focus
    refined_priority = payload.get("priority_points") if isinstance(payload.get("priority_points"), list) else priority_points
    refined_plan = payload.get("phase_plan") if isinstance(payload.get("phase_plan"), list) else phase_plan
    raw_summary = str(payload.get("raw_summary") or "").strip()
    return refined_focus, refined_priority, refined_plan, raw_summary


def run_syllabus_analysis_job(db_path: str, analysis_id: int) -> None:
    conn = sqlite3.connect(db_path)
    try:
        mark_syllabus_analysis_running(conn, analysis_id)
        conn.commit()
        analysis = get_syllabus_analysis(conn, analysis_id)
        if not analysis:
            raise RuntimeError("分析任务不存在")
        user_id = int(analysis["user_id"])
        subject = analysis["subject"]
        source_ids = analysis.get("source_ids") or []
        ensure_builtin_408_points(conn, user_id, subject)
        source_rows = _source_rows(conn, user_id, subject, source_ids)
        text = _source_text(source_rows)
        if not text.strip():
            raise RuntimeError("已选资料没有可分析的文字")
        points = list_user_knowledge_points(conn, user_id, limit=1000, subject=subject)
        ranked = _rank_points(points, text)
        if not ranked:
            ranked = _fallback_priority_points(points)
        priority_points = ranked[:24]
        school_focus = _build_school_focus(priority_points)
        phase_plan = _build_phase_plan(priority_points)
        school_focus, priority_points, phase_plan, raw_summary = _llm_refine_analysis(
            subject=subject,
            source_text=text,
            school_focus=school_focus,
            priority_points=priority_points,
            phase_plan=phase_plan,
        )
        save_syllabus_analysis_result(
            conn,
            analysis_id,
            school_focus=school_focus[:8],
            priority_points=priority_points[:30],
            phase_plan=phase_plan[:5],
            raw_summary=raw_summary,
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        mark_syllabus_analysis_failed(conn, analysis_id, str(exc))
        conn.commit()
    finally:
        conn.close()
