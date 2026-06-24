"""Personal recommendation helper for the school popularity page."""

from __future__ import annotations

import json
from typing import Any, Callable


def _safe_profile(get_profile_fn: Callable[[int], dict[str, Any]] | None, user_id: int) -> dict[str, Any]:
    if not get_profile_fn:
        return {}
    try:
        profile = get_profile_fn(user_id)
        return profile if isinstance(profile, dict) else {}
    except Exception:
        return {}


def _safe_json_list(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item]
        except json.JSONDecodeError:
            return [part.strip() for part in raw.replace("，", ",").split(",") if part.strip()]
    return []


def _fallback_recommendation(profile: dict[str, Any], school_data: dict[str, Any]) -> str:
    heat = int(school_data.get("compositeHeat") or 60)
    level = school_data.get("heatLevel", {}).get("label", "竞争中等")
    school = school_data.get("_school") or school_data.get("query", {}).get("school") or "目标院校"
    major = school_data.get("_major") or school_data.get("query", {}).get("major") or profile.get("target_major") or "目标专业"
    weak_subjects = _safe_json_list(profile.get("weak_subjects"))
    strong_subjects = _safe_json_list(profile.get("strong_subjects"))

    target_score = 360 if heat >= 80 else 345 if heat >= 65 else 330
    weak_text = "、".join(weak_subjects) if weak_subjects else "尚未填写"
    strong_text = "、".join(strong_subjects) if strong_subjects else "尚未填写"

    return f"""### AI 个性化报考建议

**1. 竞争判断**

{school} {major} 当前热度约为 **{heat}/100**，属于 **{level}**。建议把公开招生目录、复试名单和拟录取名单作为最终依据，本页结果主要用于确定复习强度和备选梯度。

**2. 备考目标**

建议先把初试目标分设在 **{target_score}+** 附近，再根据近三年复试线动态调整。强科：{strong_text}；弱科：{weak_text}。弱科每天保留固定时间，强科用于拉开总分差距。

**3. 院校组合**

保留一个冲刺目标、一个匹配目标和一个稳妥目标。若后续发现报录比持续走高，优先增加真题复盘和专业课资料整理，不建议只靠临考押题解决风险。
"""


def generate_recommendation(
    user_id: int,
    school_data: dict[str, Any],
    get_profile_fn: Callable[[int], dict[str, Any]] | None = None,
    call_llm_fn: Callable[..., str] | None = None,
) -> str:
    """Generate a personalized application suggestion.

    The function prefers the app's existing LLM caller and falls back to a
    deterministic local recommendation when the API is unavailable.
    """

    profile = _safe_profile(get_profile_fn, user_id)
    if not profile:
        return ""

    prompt = f"""你是考研择校与复习规划顾问。请基于用户画像和院校热度数据，给出简洁、谨慎、可执行的建议。

要求：
- 不编造官方数据。
- 明确说明热度结果仅供备考参考。
- 输出 Markdown，分为：竞争判断、备考目标、院校组合。
- 语气专业克制，不承诺录取结果。

用户画像：
{json.dumps(profile, ensure_ascii=False, indent=2)}

院校热度数据：
{json.dumps(school_data, ensure_ascii=False, indent=2)}
"""

    if call_llm_fn:
        try:
            result = call_llm_fn(prompt, max_tokens=1200)
            if result and result.strip():
                return result.strip()
        except Exception:
            pass

    return _fallback_recommendation(profile, school_data)
