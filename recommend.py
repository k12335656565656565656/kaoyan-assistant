"""
Recommendation engine for kaoyan-assistant.
Combines user profile data with school popularity predictions
to generate personalized application advice via LLM.

Design: no imports from app.py — get_user_profile and call_llm_api
are passed in as callable arguments to avoid circular imports.
"""
import json


# ── Constants ──

RECOMMENDATION_PROMPT_TEMPLATE = """你是考研择校与学习规划专家。请结合以下用户画像和院校热度数据，生成一份个性化报考建议报告。

## 用户画像
{profile_text}

## 院校预测数据
- 学校：{school}
- 专业：{major}
- 综合热度：{compositeHeat}/100（{heatLevel_label}）
- 数据热度：{dataHeat}/100（报录比+复试线+趋势）
- 媒体热度：{mediaHeat}/100（各平台讨论度）
- 综合置信度：{confidence}%
- 整体趋势：{trend}

### 历年录取数据
{history_text}

### {session}届预测
- 预计报考人数：{estimatedApplicants}人
- 预计报录比：{estimatedRatio}:1
- 预计复试线：{estimatedCutScore}分

### 院校信息
- 院校层次：{schoolLevel}
- 推免情况：{pushRatioDesc}

## 输出要求
请以通顺连贯的段落输出以下四部分内容，用"### "作为二级标题区分，每部分3-5句话，语气亲切专业，像一位有经验的学长/学姐在给你分析：

### 风险评估
结合用户当前水平（本科级别、成绩、是否跨考）与院校热度/报录比/复试线，客观评估报考该院校的整体难度和风险等级。如果用户有焦虑程度信息，适当安抚。

### 差距分析
将用户画像中的具体指标（英语CET分数、数学类型、强弱科目、当前阶段）与目标院校的要求做对比，指出最需要关注和提升的方向。每一点都要引用用户的具体数据来说话。

### 学习策略
针对性给出备考建议——每日学习时长、各科时间分配优先级、当前阶段（基础/强化/冲刺）的重点任务、根据弱科给出专项提升建议。

### 备选院校建议
根据用户的本科院校级别、风险偏好、目标专业和地区，推荐2-3所层次相近或略低的备选院校，简要说明推荐理由。如果用户画像信息不足以做具体推荐，则给出通用的备选策略。

---
注意：
- 如果用户画像中某些字段缺失（显示"未知"或"未设置"），不要编造，自然跳过即可
- 关于分数线、报录比等关键数据，以提供的预测数据为准，不要自己编数字
- 鼓励为主，但也要客观指出困难
- 所有建议都要联系用户的具体情况，不要说空话"""


# ── Inlined helpers (avoid circular imports from app.py) ──

def _safe_json_loads(raw, default=None):
    """Parse JSON string safely, returning default on failure."""
    if default is None:
        default = []
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def _display_target_schools_text(profile):
    """Format target_schools JSON into readable text."""
    raw = profile.get("target_schools")
    if not raw:
        return ""
    data = _safe_json_loads(raw, {})
    if isinstance(data, dict):
        parts = [f"{k}: {v}" for k, v in data.items() if v]
        return " · ".join(parts) if parts else ""
    return str(raw)


# ── Core functions ──

def extract_profile_context(profile: dict) -> dict:
    """
    Parse and normalize user profile into a flat dict of
    human-readable labels. Skips empty/null fields.
    Returns dict with Chinese labels as keys.
    """
    if not profile:
        return {}

    ctx = {}

    # Simple string/text fields: direct mapping
    for key, label in [
        ("grade", "年级"),
        ("major", "专业"),
        ("undergraduate_school", "本科院校"),
        ("undergraduate_major", "本科专业"),
        ("undergraduate_level", "本科院校级别"),
        ("is_cross_major", "是否跨考"),
        ("target_major", "目标专业"),
        ("target_region", "目标地区"),
        ("target_year", "目标年份"),
        ("risk_preference", "风险偏好"),
        ("current_phase", "当前阶段"),
        ("math_exam_type", "数学考试类型"),
        ("schedule_preference", "作息偏好"),
        ("material_preference", "资料偏好"),
        ("procrastination_type", "拖延类型"),
        ("motivation_preference", "激励偏好"),
    ]:
        val = profile.get(key)
        if val and str(val).strip():
            ctx[label] = str(val).strip()

    # Numeric fields
    if profile.get("daily_hours"):
        ctx["每日学习时长"] = f"{profile['daily_hours']}小时"

    if profile.get("cet4_score"):
        ctx["CET-4成绩"] = f"{profile['cet4_score']}分"

    if profile.get("cet6_score"):
        ctx["CET-6成绩"] = f"{profile['cet6_score']}分"

    anxiety = profile.get("anxiety_level")
    if anxiety is not None and anxiety != "":
        try:
            ctx["焦虑程度"] = f"{int(anxiety)}/5"
        except (ValueError, TypeError):
            pass

    # JSON array fields
    weak = _safe_json_loads(profile.get("weak_subjects"))
    if weak:
        ctx["弱科"] = "、".join(weak)

    strong = _safe_json_loads(profile.get("strong_subjects"))
    if strong:
        ctx["强科"] = "、".join(strong)

    errors = _safe_json_loads(profile.get("common_errors"))
    if errors:
        ctx["常见错误"] = "、".join(errors)

    # Target schools
    schools_text = _display_target_schools_text(profile)
    if schools_text:
        ctx["目标院校"] = schools_text

    # Mock scores
    mock = _safe_json_loads(profile.get("mock_scores"), {})
    if isinstance(mock, dict) and mock:
        parts = [f"{k}:{v}分" for k, v in mock.items() if v]
        if parts:
            ctx["模考成绩"] = " · ".join(parts)
    elif isinstance(mock, list) and mock:
        ctx["模考成绩"] = f"共{len(mock)}次记录"

    return ctx


def build_recommendation_prompt(context: dict, prediction_data: dict) -> str:
    """
    Build the LLM prompt by combining user profile context and
    school prediction data. Returns a formatted Chinese prompt string.
    """
    # Profile section
    if context:
        profile_lines = "\n".join(f"- {k}：{v}" for k, v in context.items())
    else:
        profile_lines = "（用户尚未填写个人画像）"

    # Prediction fields
    heat = prediction_data.get("compositeHeat", 0)
    level = prediction_data.get("heatLevel", {})
    si = prediction_data.get("schoolInfo", {})
    pred = prediction_data.get("prediction", {})

    # Admission history
    history_lines = []
    for h in prediction_data.get("admissionHistory", []):
        note_tag = f" [{h['note']}]" if h.get("note") else ""
        history_lines.append(
            f"  {h['year']}年: 报考{h['applicants']}人 / "
            f"录取{h['admitted']}人 / 报录比{h['ratio']}:1 / "
            f"复试线{h['cutScore']}分{note_tag}"
        )
    history_text = "\n".join(history_lines) if history_lines else "暂无历年数据"

    # Determine session from prediction
    session = prediction_data.get("session", prediction_data.get("_session", "27届"))

    prompt = RECOMMENDATION_PROMPT_TEMPLATE.format(
        profile_text=profile_lines,
        school=prediction_data.get("_school", prediction_data.get("school", "未知")),
        major=prediction_data.get("_major", prediction_data.get("major", "未知")),
        compositeHeat=heat,
        heatLevel_label=level.get("label", "未知"),
        dataHeat=prediction_data.get("dataHeat", 0),
        mediaHeat=prediction_data.get("mediaHeat", 0),
        confidence=prediction_data.get("confidence", 0),
        trend=prediction_data.get("trend", "稳定"),
        history_text=history_text,
        session=session,
        estimatedApplicants=pred.get("estimatedApplicants", "?"),
        estimatedRatio=pred.get("estimatedRatio", "?"),
        estimatedCutScore=pred.get("estimatedCutScore", "?"),
        schoolLevel=si.get("schoolLevel", "未知"),
        pushRatioDesc=si.get("pushRatioDesc", "暂无数据"),
    )
    return prompt


def generate_recommendation(user_id, prediction_data, get_profile_fn, call_llm_fn):
    """
    Top-level entry point. Fetches user profile, builds prompt,
    calls LLM, and returns the recommendation text.

    Args:
        user_id: user ID for profile lookup
        prediction_data: dict from kaoyan_predict.normalize_for_ui()
        get_profile_fn: callable(user_id) -> profile dict or {}
        call_llm_fn: callable(prompt, model, max_tokens) -> str

    Returns:
        Recommendation text string, or empty string if no profile available.
    """
    profile = get_profile_fn(user_id)
    if not profile:
        return ""

    context = extract_profile_context(profile)
    prompt = build_recommendation_prompt(context, prediction_data)
    return call_llm_fn(prompt, model="mimo-v2.5", max_tokens=2000)
