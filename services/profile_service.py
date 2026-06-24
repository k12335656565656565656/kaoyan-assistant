from __future__ import annotations

import json
import re
from typing import Any, Callable

from repositories.profile_repo import get_user_profile as get_user_profile_repo
from repositories.profile_repo import save_profile_field as save_profile_field_repo
from repositories.profile_repo import save_profile_fields as save_profile_fields_repo


PROFILE_REQUIRED_FIELDS = ["grade", "major", "target_major", "daily_hours"]

PHASE_LABELS = ["基础阶段", "强化阶段", "提升阶段", "冲刺阶段"]


def safe_json_loads(raw, default=None):
    if default is None:
        default = []
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def display_target_schools(profile: dict) -> str:
    raw = profile.get("target_schools")
    if not raw:
        return "未设置"
    data = safe_json_loads(raw, {})
    if isinstance(data, dict):
        parts = [f"{key}: {value}" for key, value in data.items() if value]
        return " · ".join(parts) if parts else "未设置"
    return str(raw)


def profile_is_complete(profile: dict) -> bool:
    return all(profile.get(field) for field in PROFILE_REQUIRED_FIELDS)


def auto_generate_tags(profile: dict) -> dict:
    tags = {
        "common_errors": [],
        "strong_areas": [],
        "current_phase": profile.get("current_phase") or "基础",
    }
    weak_subjects = safe_json_loads(profile.get("weak_subjects"))
    strong_subjects = safe_json_loads(profile.get("strong_subjects"))
    if "数学" in weak_subjects:
        tags["common_errors"].extend(["计算错误", "公式混淆"])
    if "英语" in weak_subjects:
        tags["common_errors"].extend(["语法错误", "词汇量不足"])
    if "政治" in weak_subjects:
        tags["common_errors"].append("知识点遗漏")
    if "专业课" in weak_subjects:
        tags["common_errors"].append("概念理解偏差")
    if "数学" in strong_subjects:
        tags["strong_areas"].extend(["逻辑推理", "公式应用"])
    if "英语" in strong_subjects:
        tags["strong_areas"].append("阅读理解")
    if "政治" in strong_subjects:
        tags["strong_areas"].append("时政敏感度")
    tags["common_errors"] = list(dict.fromkeys(tags["common_errors"]))
    tags["strong_areas"] = list(dict.fromkeys(tags["strong_areas"]))
    return tags


def persist_auto_tags(db_path: str, user_id: int) -> dict:
    profile = get_user_profile_repo(db_path, user_id)
    tags = auto_generate_tags(profile)
    save_profile_fields_repo(
        db_path,
        user_id,
        {
            "common_errors": json.dumps(tags["common_errors"], ensure_ascii=False),
            "strong_areas": json.dumps(tags["strong_areas"], ensure_ascii=False),
            "current_phase": tags["current_phase"],
        },
    )
    return tags


def rule_extract_profile(query: str) -> dict:
    result = {}
    school_match = re.search(r"(清华|北大|复旦|上交|浙大|中科大|南大|武大|目标.*?([^\s，。]+))", query)
    if school_match:
        result["target_school"] = school_match.group(1).replace("目标", "").strip("是")
    if "焦虑" in query or "崩溃" in query:
        result["anxiety_level"] = 4
    for phase in ("基础", "强化", "冲刺", "模考"):
        if phase in query:
            result["current_phase"] = phase
            break
    for math_type in ("数一", "数二", "数三", "199管综"):
        if math_type in query:
            result["math_type"] = math_type
            break
    return result


def extract_profile_from_conversation(
    query: str,
    answer: str,
    *,
    llm_call: Callable[[str], str] | None = None,
) -> dict:
    extracted = {}
    if llm_call is not None:
        prompt = f"""从以下对话中提取用户信息，返回 JSON 格式：
用户：{query}
AI：{answer}
请提取以下信息（如果有的话）：target_major, target_school, math_type, weak_subject, anxiety_level(1-5整数), current_phase(基础/强化/冲刺/模考)
只返回 JSON，不要其他内容。如果没有信息，返回空 JSON {{}}"""
        try:
            text = llm_call(prompt).strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            extracted = json.loads(text)
        except Exception:
            extracted = {}
    if not extracted:
        extracted = rule_extract_profile(query)
    return extracted


def update_profile_from_conversation(
    db_path: str,
    user_id: int,
    query: str,
    answer: str,
    *,
    llm_call: Callable[[str], str] | None = None,
) -> dict:
    extracted = extract_profile_from_conversation(query, answer, llm_call=llm_call)
    field_map = {
        "target_major": "target_major",
        "math_type": "math_exam_type",
        "anxiety_level": "anxiety_level",
        "current_phase": "current_phase",
    }
    for source, target in field_map.items():
        if extracted.get(source):
            save_profile_field_repo(db_path, user_id, target, extracted[source])

    if extracted.get("target_school"):
        schools = safe_json_loads(get_user_profile_repo(db_path, user_id).get("target_schools"), {})
        schools["冲刺"] = extracted["target_school"]
        save_profile_field_repo(db_path, user_id, "target_schools", json.dumps(schools, ensure_ascii=False))

    if extracted.get("weak_subject"):
        weak_subjects = safe_json_loads(get_user_profile_repo(db_path, user_id).get("weak_subjects"))
        if extracted["weak_subject"] not in weak_subjects:
            weak_subjects.append(extracted["weak_subject"])
        save_profile_field_repo(db_path, user_id, "weak_subjects", json.dumps(weak_subjects, ensure_ascii=False))

    return extracted


def build_profile_form_payload(
    *,
    target_school: str,
    target_major: str,
    undergraduate_major: str,
    undergraduate_level: str,
    is_cross_major: str,
    strong_subjects: list[str],
    weak_subjects: list[str],
    anxiety_level: int,
) -> dict[str, Any]:
    return {
        "target_schools": json.dumps({"冲刺": target_school}, ensure_ascii=False) if target_school else "",
        "target_major": target_major,
        "undergraduate_major": undergraduate_major,
        "undergraduate_level": undergraduate_level,
        "is_cross_major": is_cross_major,
        "strong_subjects": json.dumps(strong_subjects, ensure_ascii=False),
        "weak_subjects": json.dumps(weak_subjects, ensure_ascii=False),
        "anxiety_level": anxiety_level,
    }


def save_profile_form(db_path: str, user_id: int, **payload) -> None:
    save_profile_fields_repo(db_path, user_id, build_profile_form_payload(**payload))


def build_profile_display_items(profile: dict) -> list[tuple[str, str]]:
    return [
        ("目标院校", display_target_schools(profile)),
        ("目标专业", profile.get("target_major") or "未设置"),
        ("本专业", profile.get("undergraduate_major") or "未设置"),
        ("本科院校级别", profile.get("undergraduate_level") or "未设置"),
        ("是否跨考", profile.get("is_cross_major") or "否"),
        ("强科", ", ".join(safe_json_loads(profile.get("strong_subjects"))) or "未设置"),
        ("弱科", ", ".join(safe_json_loads(profile.get("weak_subjects"))) or "未设置"),
        ("焦虑程度", f"{profile.get('anxiety_level') or '未设置'}/5"),
    ]


def build_recommendation_profile_caption(profile: dict) -> str:
    summary_parts = []
    if profile.get("undergraduate_level"):
        summary_parts.append(f"本科{profile['undergraduate_level']}")
    if profile.get("grade"):
        summary_parts.append(profile["grade"])
    if profile.get("target_major"):
        summary_parts.append(f"目标{profile['target_major']}")
    return " · ".join(summary_parts)
