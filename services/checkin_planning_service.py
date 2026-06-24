from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Callable


FLOW_FALLBACKS = {
    "清晨": [
        "清晨的每一分钟都在为未来铺路，今天加油。",
        "趁晨光正好，开启专注的一天。",
        "早起的你，已经领先了大多数人。",
    ],
    "上午": [
        "上午是大脑最清醒的时段，保持这份专注。",
        "稳步推进，今天的目标正在靠近。",
        "按自己的节奏来，每一步都算数。",
    ],
    "午间": [
        "适当休整后继续，下午还有目标等你。",
        "短暂的休息是为了更好的出发。",
        "保持节奏，不急不躁。",
    ],
    "下午": [
        "下午是攻坚的好时段，持续推进。",
        "还有半天的机会，把进度再推一步。",
        "专注当下，完成比完美更重要。",
    ],
    "晚间": [
        "今天的坚持值得肯定，回顾一下收获。",
        "夜深人静正是深度学习时，但别太晚。",
        "复盘今日所学，让努力有迹可循。",
    ],
    "深夜": [
        "夜深了，今天的努力已足够，早点休息。",
        "身体是革命的本钱，明天再战。",
        "今天的每一分钟都不会白费，晚安。",
    ],
}

PHASE_GUIDE_ROWS = [
    ("基础阶段", "3-6月", "全面打基础、吃透教材和基础题"),
    ("强化阶段", "7-9月", "专项突破、大量刷题、建立做题体系"),
    ("提升阶段", "10-11月", "真题实战、查漏补缺、模考检验"),
    ("冲刺阶段", "12月", "高频考点押题、心理调整、保持手感"),
]

PHASE_TEMPLATES = {
    "基础阶段": {
        "数学": ["教材通读", "基础概念理解", "基础题型练习", "公式推导"],
        "英语": ["词汇积累", "长难句解析", "阅读基础", "写作基础"],
        "政治": ["教材通读", "基本概念理解", "选择题练习"],
        "专业课": ["教材通读", "核心概念理解", "基础题型练习"],
    },
    "强化阶段": {
        "数学": ["专项突破", "大量刷题", "错题整理", "知识体系建立"],
        "英语": ["阅读强化", "写作强化", "翻译强化", "新题型练习"],
        "政治": ["重点章节强化", "选择题强化", "分析题练习"],
        "专业课": ["重点章节强化", "真题研究", "专题训练"],
    },
    "提升阶段": {
        "数学": ["真题实战", "查漏补缺", "模考检验", "高频考点强化"],
        "英语": ["真题实战", "写作模板", "阅读技巧", "完形填空"],
        "政治": ["真题实战", "时政热点", "分析题强化", "模拟考试"],
        "专业课": ["真题实战", "模拟考试", "重点难点突破"],
    },
    "冲刺阶段": {
        "数学": ["高频考点押题", "错题回顾", "公式速记", "模拟考试"],
        "英语": ["作文模板强化", "阅读技巧", "词汇巩固", "模拟考试"],
        "政治": ["时政热点", "分析题押题", "选择题速刷", "模拟考试"],
        "专业课": ["高频考点", "模拟考试", "重点难点回顾"],
    },
}

RECOVERY_STRATEGIES = {
    1: {"name": "删减低频考点", "description": "剔除近5年未考的知识点", "trigger": "deviation > 20%", "action": "删除低频考点任务，聚焦高频内容"},
    2: {"name": "聚焦高频核心", "description": "集中精力攻克高频+必考内容", "trigger": "deviation > 30%", "action": "将高频考点任务优先级提升为最高"},
    3: {"name": "压缩次要科目", "description": "提高优势科目用时，控制短板科目投入", "trigger": "deviation > 25%", "action": "调整科目权重，增加优势科目时间"},
    4: {"name": "切换速通模式", "description": "只看知识框架 + 重点题型，不全做", "trigger": "deviation > 40%", "action": "简化任务内容，只保留核心框架"},
    5: {"name": "错题优先", "description": "优先做错题，而非刷新题", "trigger": "连续3天完成率 < 60%", "action": "将错题复习任务优先级提升"},
    6: {"name": "调整作息", "description": "增加每日有效学习时长", "trigger": "连续5天完成率 < 70%", "action": "建议调整作息，增加学习时长"},
}


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except Exception:
        return default


def build_checkin_reminders(
    *,
    recent_records: list[Any],
    last_date: str | None,
    streak: int,
    plan_progress: float,
    today: date | None = None,
) -> list[tuple[str, str]]:
    reminders: list[tuple[str, str]] = []
    today = today or date.today()

    expected_dates = [(today - timedelta(days=index)).strftime("%Y-%m-%d") for index in range(3)]
    recent_dates = [_row_value(row, "checkin_date") for row in recent_records]
    low_completion = all(float(_row_value(row, "completion_rate", 0) or 0) < 60 for row in recent_records)
    if recent_dates == expected_dates and len(recent_records) == 3 and low_completion:
        reminders.append(("warning", "连续 3 天完成率低于 60%，建议降低任务颗粒度。"))

    if last_date:
        gap = (today - datetime.strptime(last_date, "%Y-%m-%d").date()).days
        if gap >= 7:
            reminders.append(("error", f"已经 {gap} 天没有打卡了，建议今天先完成一个小任务。"))
    else:
        reminders.append(("info", "还没有打卡记录，先完成今天的第一次打卡。"))

    if streak in {7, 21, 50, 100}:
        reminders.append(("success", f"连续打卡 {streak} 天，已达成阶段里程碑。"))

    if 0 < plan_progress < 80:
        reminders.append(("warning", f"当前活跃计划平均完成率 {plan_progress}%，低于 80%，建议复盘。"))

    return reminders


def get_time_period(now: datetime | None = None) -> str:
    now = now or datetime.now()
    hour = now.hour
    if 5 <= hour < 9:
        return "清晨"
    if 9 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "午间"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 22:
        return "晚间"
    return "深夜"


def build_flow_focus_data(
    *,
    today_minutes: int,
    pomodoro_minutes: int,
    goal_hours: float,
    checked_in: bool,
    mood: str | None,
    streak: int,
) -> dict[str, Any]:
    total_minutes = max(today_minutes, pomodoro_minutes) if pomodoro_minutes else today_minutes
    goal_minutes = goal_hours * 60
    progress_pct = min(round(total_minutes / goal_minutes * 100) if goal_minutes > 0 else 0, 100)
    return {
        "total_hours": round(total_minutes / 60, 1),
        "total_minutes": total_minutes,
        "goal_hours": goal_hours,
        "progress_pct": progress_pct,
        "checked_in": checked_in,
        "mood": mood,
        "streak": streak,
    }


def pick_flow_message(*, data: dict[str, Any], period: str) -> str:
    candidates = FLOW_FALLBACKS.get(period, FLOW_FALLBACKS["上午"])
    pct = int(data.get("progress_pct") or 0)
    streak = int(data.get("streak") or 0)

    if pct == 0 and streak >= 7:
        index = 0
    elif pct >= 80:
        index = 1
    elif pct >= 50:
        index = 0
    else:
        index = min(pct // 30, len(candidates) - 1)

    if period == "深夜" and pct >= 80:
        return "今日目标已达成，这份坚持值得骄傲，去休息吧。"

    return candidates[index]


def build_flow_message_prompt(*, data: dict[str, Any], period: str) -> str:
    return f"""你是考研备考助手。根据以下用户数据，生成一句"今日心流寄语"。

## 用户数据
- 当前时段：{period}
- 今日已学习：{data['total_hours']} 小时（每日目标 {data['goal_hours']} 小时）
- 目标完成度：{data['progress_pct']}%
- 今日是否已打卡：{'是' if data['checked_in'] else '否'}
- 今日心情：{data['mood'] or '未记录'}
- 连续打卡：{data['streak']} 天

## 输出要求
1. 只输出一句话（15-30 字），不加前缀、引号或解释
2. 语气朴素理性，不使用"亲爱的""孩子""老师""同学"等称呼
3. 时段对应态度：
   - 清晨：鼓励开启新一天，简短有力
   - 上午：肯定早间努力，提醒保持节奏
   - 午间：提醒适当休息，储备下午精力
   - 下午：关注进度推进，给予方向感
   - 晚间：回顾今日收获，肯定坚持
   - 深夜：温和提醒休息，不鼓励透支
4. 完成度对应态度：
   - 0%（未开始）：温和提醒，不施加压力
   - 1-50%：鼓励推进，肯定已付出的努力
   - 50-80%：肯定进展，提醒保持节奏
   - 80%+：赞赏坚持，鼓励收尾
5. 连续打卡 ≥ 7 天时可含蓄肯定习惯的力量"""


def determine_phase(now: datetime | None = None) -> str:
    now = now or datetime.now()
    month = now.month
    if 3 <= month <= 6:
        return "基础阶段"
    if 7 <= month <= 9:
        return "强化阶段"
    if 10 <= month <= 11:
        return "提升阶段"
    if month == 12:
        return "冲刺阶段"
    return "基础阶段"


def build_phase_guide_rows() -> list[tuple[str, str, str]]:
    return list(PHASE_GUIDE_ROWS)


def get_subject_weights(math_type: str) -> dict[str, float]:
    weights = {
        "数一": {"数学": 0.35, "英语": 0.20, "政治": 0.15, "专业课": 0.30},
        "数二": {"数学": 0.35, "英语": 0.20, "政治": 0.15, "专业课": 0.30},
        "数三": {"数学": 0.35, "英语": 0.20, "政治": 0.15, "专业课": 0.30},
        "不考数学": {"英语": 0.30, "政治": 0.20, "专业课": 0.50},
        "199管综": {"管综": 0.40, "英语": 0.30, "政治": 0.15, "专业课": 0.15},
    }
    return dict(weights.get(math_type, weights["数一"]))


def calculate_daily_hours(daily_hours: float, math_type: str) -> dict[str, float]:
    weights = get_subject_weights(math_type)
    return {subject: round(daily_hours * weight, 1) for subject, weight in weights.items()}


def select_recovery_strategy(deviation: float, recent_completion_rates: list[float]) -> list[int]:
    strategies = []
    if deviation > 40:
        strategies.append(4)
    if deviation > 30:
        strategies.append(2)
    if deviation > 25:
        strategies.append(3)
    if deviation > 20:
        strategies.append(1)
    if len(recent_completion_rates) >= 3:
        avg_rate = sum(recent_completion_rates[:3]) / 3
        if avg_rate < 60:
            strategies.append(5)
    if len(recent_completion_rates) >= 5:
        avg_rate5 = sum(recent_completion_rates[:5]) / 5
        if avg_rate5 < 70:
            strategies.append(6)
    return strategies


def _normalize_profile_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _apply_weak_subject_weights(weights: dict[str, float], weak_subjects: list[str]) -> dict[str, float]:
    if not weak_subjects:
        return weights
    tuned = dict(weights)
    for subject in weak_subjects:
        if subject in tuned:
            tuned[subject] = min(tuned[subject] * 1.2, 0.45)
    total = sum(tuned.values()) or 1.0
    return {key: round(value / total, 3) for key, value in tuned.items()}


def _build_plan_tasks(
    *,
    weights: dict[str, float],
    phase: str,
    daily_hours: float,
    weak_subjects: list[str],
) -> list[dict[str, Any]]:
    tasks = []
    for subject, weight in weights.items():
        subject_hours = daily_hours * weight
        task_list = PHASE_TEMPLATES.get(phase, {}).get(subject, [])
        priority = 1 if subject in weak_subjects else 3
        for task_name in task_list:
            tasks.append(
                {
                    "subject": subject,
                    "task_name": task_name,
                    "estimated_hours": round(subject_hours / max(len(task_list), 1), 1),
                    "priority": priority,
                }
            )
    return tasks


def generate_plan_bundle(
    *,
    user_profile: dict[str, Any],
    target_date: date,
    math_type: str,
    daily_hours: float,
    llm_call: Callable[[str], str],
    display_target_schools_fn: Callable[[dict[str, Any]], str],
    json_loads_fn: Callable[[Any, Any], Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now()
    weights = get_subject_weights(math_type)
    phase = determine_phase(now)
    days_remaining = (target_date - now.date()).days

    weak_subjects = _normalize_profile_list(json_loads_fn(user_profile.get("weak_subjects"), []))
    strong_subjects = _normalize_profile_list(json_loads_fn(user_profile.get("strong_subjects"), []))
    target_major = user_profile.get("target_major") or ""
    target_schools = display_target_schools_fn(user_profile)
    anxiety_level = user_profile.get("anxiety_level")
    undergraduate_major = user_profile.get("undergraduate_major") or ""
    undergraduate_level = user_profile.get("undergraduate_level") or ""
    is_cross_major = user_profile.get("is_cross_major") or ""

    weights = _apply_weak_subject_weights(weights, weak_subjects)
    daily_sub_hours = {subject: round(daily_hours * weight, 1) for subject, weight in weights.items()}
    tasks = _build_plan_tasks(
        weights=weights,
        phase=phase,
        daily_hours=daily_hours,
        weak_subjects=weak_subjects,
    )

    profile_lines = []
    if target_schools and target_schools != "未设置":
        profile_lines.append(f"- 目标院校：{target_schools}")
    if target_major:
        profile_lines.append(f"- 目标专业：{target_major}")
    if undergraduate_major:
        profile_lines.append(f"- 本专业：{undergraduate_major}")
    if undergraduate_level:
        profile_lines.append(f"- 本科院校级别：{undergraduate_level}")
    if is_cross_major == "是":
        profile_lines.append("- 是否跨考：是（跨考生需额外注意专业课基础）")
    if weak_subjects:
        profile_lines.append(f"- 弱科：{', '.join(weak_subjects)}")
    if strong_subjects:
        profile_lines.append(f"- 强科：{', '.join(strong_subjects)}")
    if anxiety_level:
        profile_lines.append(f"- 焦虑程度：{anxiety_level}/5")

    profile_text = "\n".join(profile_lines) if profile_lines else "（用户尚未填写画像信息）"
    prompt = f"""你是考研学习规划专家。请生成一份结构化的学习时间表。

## 用户画像
{profile_text}
- 每日学习时长：{daily_hours}小时
- 数学类型：{math_type}

## 考试规划
- 目标日期：{target_date.strftime("%Y-%m-%d")}
- 剩余天数：{days_remaining}天
- 当前阶段：{phase}
- 各科权重：{json.dumps(weights, ensure_ascii=False)}

## 输出格式要求

请以 **Markdown 表格 + 简要说明** 的格式输出，不要长篇抒情，语气简洁专业：

### 1. 每日时间表
用表格输出，例如：
```
| 时间段 | 科目 | 任务重点 | 建议时长 |
|--------|------|----------|----------|
| 08:00-12:00 | 数学 | 专题突破+真题训练 | 4h |
| 14:00-17:00 | 英语 | 阅读理解+单词 | 3h |
| 19:00-21:00 | 政治 | 章节梳理+选择题 | 2h |
| 21:00-22:00 | 总结整理 | 错题回顾+明日计划 | 1h |
```

### 2. 时间段分配原则
- 上午安排需要高度专注的科目（如数学、专业课）
- 下午安排语言类科目（如英语）
- 晚上安排记忆和政治类科目
- 根据弱科（{', '.join(weak_subjects) if weak_subjects else '无'}）优先分配黄金时间段
- 每科之间留10-15分钟休息

### 3. 每周计划概述
- 周一至周五：按时间表执行
- 周六：模拟测试+批改分析
- 周日：本周错题复习+下周计划调整

请直接输出，无需额外说明。"""
    description = llm_call(prompt)
    return {
        "description": description,
        "tasks": tasks,
        "phase": phase,
        "weights": weights,
        "daily_sub_hours": daily_sub_hours,
    }


def build_checkin_plan_prompt(
    *,
    profile: dict[str, Any],
    plan_phase: str,
    plan_subjects: list[str],
    daily_hours: float,
    display_target_schools_fn: Callable[[dict[str, Any]], str],
    json_loads_fn: Callable[[Any, Any], Any],
) -> str:
    target_schools = display_target_schools_fn(profile)
    target_major = profile.get("target_major") or "未设置"
    undergraduate_major = profile.get("undergraduate_major") or "未设置"
    undergraduate_level = profile.get("undergraduate_level") or "未设置"
    strong_subjects = json_loads_fn(profile.get("strong_subjects"), [])
    weak_subjects = json_loads_fn(profile.get("weak_subjects"), [])
    is_cross_major = profile.get("is_cross_major") or "否"
    anxiety = profile.get("anxiety_level") or 3

    subjects_str = "、".join(plan_subjects)
    gap_desc = ""
    if target_schools and target_schools != "未设置":
        gap_desc = f"目标院校：{target_schools}，目标专业：{target_major}"
        if undergraduate_level and undergraduate_level != "未设置":
            gap_desc += f"，本科院校：{undergraduate_level}"
        if is_cross_major == "是":
            gap_desc += "，跨考生"

    return f"""结合用户基础和院校差距，生成一份实用、可执行的学习计划。

## 用户画像
- {gap_desc if gap_desc else '目标院校：未设置'}
- 本专业：{undergraduate_major}
- 强科：{', '.join(strong_subjects) if strong_subjects else '未设置'}
- 弱科：{', '.join(weak_subjects) if weak_subjects else '未设置'}
- 焦虑程度：{anxiety}/5
- 当前阶段：{plan_phase}
- 学习科目：{subjects_str}
- 每日学习时长：{daily_hours}小时

## 输出要求
请按科目分段，每段给出具体的复习安排和建议。
要求：
1. 直接给出复习安排，不写鼓励、共情或称呼（如"亲爱的同学""孩子""老师"）
2. 语气朴素、理性，像说明文档而非个人书信
3. 结合用户的院校差距，说明该阶段的学习重点
4. 结合强弱科，给出针对性建议
5. 可用短段落 + 要点形式，总字数约 400-600 字
"""
