"""Build structured prompts for targeted reinforcement material."""

from ..models import PersonalizedRequirement, TrainingMaterialRequest


def build_training_material_request(requirement: PersonalizedRequirement):
    focus = ["核心定义", "典型题型", "易错点"]
    if requirement.tier == "标准":
        focus.append("综合应用")
    elif requirement.tier == "提高":
        focus.extend(["综合应用", "变式训练"])
    title = f"{requirement.knowledge_point_id}·{requirement.tier}强化训练"
    return TrainingMaterialRequest(
        knowledge_point_id=requirement.knowledge_point_id,
        tier=requirement.tier,
        title=title,
        focus=tuple(focus),
        evidence_summary=dict(requirement.evidence_summary),
        expected_contribution=requirement.expected_contribution,
    )


def build_training_material_prompt(request: TrainingMaterialRequest, knowledge_text: str):
    """Build a targeted prompt; the caller owns the actual LLM request."""
    evidence = request.evidence_summary
    return f"""你是考研数学强化训练教练。请只基于下面知识点内容，生成一份短而具体的强化训练资料。

知识点：{request.knowledge_point_id}
训练档位：{request.tier}
训练重点：{"、".join(request.focus)}
历史答题：答对 {evidence.get("times_correct", 0)} 次，答错 {evidence.get("times_wrong", 0)} 次
最近错误类型：{evidence.get("last_error_type") or "未记录"}

知识点原文：
{knowledge_text[:5000]}

输出结构：
# 核心定义
# 典型方法
# 易错点
# 2 道针对性练习题（给出答案和简要解析）

不要输出与该知识点无关的内容，不要编造真题出处。"""
