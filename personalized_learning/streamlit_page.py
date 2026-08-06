"""Streamlit adapter for the reusable math diagnosis and training experience."""

import html
import math
import re
from fractions import Fraction
from uuid import uuid4
from collections import OrderedDict
from typing import Iterable, Mapping, Sequence

from .math.diagnosis import build_diagnosis_plan, has_completed_diagnosis, record_diagnosis_answer
from .math.diagnosis_pool import diagnosis_generation_slots, select_diagnosis_questions
from .math.diagnosis_report import build_diagnosis_report, build_diagnosis_summary_prompt
from .math.diagnosis_variants import build_variant_batch_prompt, build_variant_questions
from .math.mastery import calculate_mastery
from .math.requirements import build_diagnostic_requirements, build_requirements
from .models import MasterySnapshot, StudentProfile, classify_question_source
from .repository import (
    ensure_schema,
    get_profile,
    get_legacy_math_exam_type,
    import_exam_questions,
    list_diagnostic_questions,
    list_eligible_exam_questions,
    list_evidence,
    repair_legacy_question_mapping_ids,
    save_evidence,
    save_profile,
)
from .training.material_generator import (
    build_training_material_prompt,
    build_training_material_request,
)


EXAM_TYPES = OrderedDict((("数学一", "math1"), ("数学二", "math2"), ("数学三", "math3")))


def resolve_math_exam_type(connection, user_id, profile=None):
    """Prefer the new goal record, then fall back to the original user portrait."""
    profile_exam_type = getattr(profile, "exam_type", None)
    if profile_exam_type in EXAM_TYPES.values():
        return profile_exam_type
    return get_legacy_math_exam_type(connection, user_id) or "math1"


def parse_generated_quiz(raw_text: str):
    """Keep compatibility with the established Q/A/ANSWER/EXPLAIN quiz format."""
    if not raw_text:
        return None
    block = next((part for part in raw_text.split("---") if "Q:" in part), "")
    if not block:
        return None
    question, options, answer, explain = "", [], "", ""
    collecting_question = False
    collecting_explain = False
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("Q:", "Q：")):
            collecting_question, collecting_explain = True, False
            question = line.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif re.match(r"^[A-E][).、]", line):
            collecting_question, collecting_explain = False, False
            options.append(line)
        elif line.startswith(("ANSWER:", "答案:", "答案：")):
            collecting_question, collecting_explain = False, False
            answer = line.split(":", 1)[-1].split("：", 1)[-1].strip().upper()
        elif line.startswith(("EXPLAIN:", "解析:", "解析：")):
            collecting_question, collecting_explain = False, True
            explain = line.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif collecting_explain:
            explain = f"{explain} {line}".strip()
        elif collecting_question:
            question = f"{question} {line}".strip()
    answer_match = re.search(r"[A-E]", answer)
    if not question and not options:
        return None
    return {"question": question, "options": options, "answer": answer_match.group(0) if answer_match else answer, "explain": explain, "raw": raw_text}


def choose_diagnosis_knowledge_points(
    knowledge_points: Sequence[Mapping[str, str]],
    mastery_by_knowledge: Mapping[str, MasterySnapshot],
    limit: int = 20,
):
    """Choose weak points first, then unseen points, without duplicate IDs."""
    normalized = []
    seen = set()
    for index, point in enumerate(knowledge_points):
        knowledge_id = str(point.get("id") or "").strip()
        if knowledge_id and knowledge_id not in seen:
            normalized.append((index, knowledge_id))
            seen.add(knowledge_id)
    weak, unseen, known = [], [], []
    for index, knowledge_id in normalized:
        snapshot = mastery_by_knowledge.get(knowledge_id)
        if snapshot is None:
            unseen.append((index, knowledge_id))
        elif snapshot.mastery < 0.7 or snapshot.times_wrong > 0:
            weak.append((snapshot.mastery, -snapshot.times_wrong, index, knowledge_id))
        else:
            known.append((snapshot.mastery, index, knowledge_id))
    selected = [item[3] for item in sorted(weak)[:limit]]
    for _, knowledge_id in unseen:
        if len(selected) >= limit:
            break
        selected.append(knowledge_id)
    for _, _, knowledge_id in sorted(known):
        if len(selected) >= limit:
            break
        selected.append(knowledge_id)
    return tuple(selected[:limit])


def count_diagnosis_questions(evidence: Iterable[object], session_id: str = "") -> int:
    return len({
        item.question_id
        for item in evidence
        if str(getattr(item, "source", "")).startswith("diagnosis")
        and (not session_id or str(getattr(item, "source", "")) == f"diagnosis:{session_id}")
    })


def _parse_numeric_answer(value):
    raw = re.sub(r"\s+", "", str(value or "").strip())
    if not raw:
        return None
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)/[+-]?(?:\d+(?:\.\d*)?|\.\d+)", raw):
        try:
            return float(Fraction(raw))
        except (ValueError, ZeroDivisionError):
            return None
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", raw):
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def is_math_answer_correct(question, user_answer):
    """Return True/False for safely comparable answers, otherwise None for review."""
    expected = str(getattr(question, "answer", "") or "").strip()
    actual = str(user_answer or "").strip()
    if not expected or not actual:
        return False

    _, options = split_question_content(getattr(question, "question_text", ""))
    if options:
        return actual.upper() == expected.upper()

    expected_number = _parse_numeric_answer(expected)
    actual_number = _parse_numeric_answer(actual)
    if expected_number is not None:
        if actual_number is None:
            return False
        return math.isclose(actual_number, expected_number, rel_tol=1e-6, abs_tol=1e-6)

    normalized_expected = re.sub(r"\s+", "", expected).casefold()
    normalized_actual = re.sub(r"\s+", "", actual).casefold()
    if normalized_expected == normalized_actual:
        return True
    return None


def _inject_exam_goal_styles(st):
    st.markdown(
        """
<style>
.stApp { background: #f3f7fb; }
.block-container { max-width: 1180px; padding-top: 1.6rem; padding-bottom: 3.5rem; }
.eg-header { display:flex; justify-content:space-between; gap:1.5rem; align-items:flex-start; margin: .15rem 0 1.25rem; }
.eg-title { margin:0; color:#1e293b; font-size:1.72rem; font-weight:750; line-height:1.25; letter-spacing:0; }
.eg-subtitle { margin:.42rem 0 0; color:#64748b; font-size:.94rem; max-width:42rem; line-height:1.6; }
.eg-section-title { margin:1.5rem 0 .65rem; color:#1e293b; font-size:1.08rem; font-weight:700; letter-spacing:0; }
.eg-profile { display:grid; grid-template-columns:minmax(0,1fr) 280px; background:#fff; border:1px solid #e2e8f0; border-radius:12px; overflow:hidden; }
.eg-profile-main { padding:1.1rem 1.2rem; }
.eg-profile-top { display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; }
.eg-profile-name { margin:0; color:#1e293b; font-size:1.04rem; font-weight:700; }
.eg-profile-copy { margin:.28rem 0 0; color:#64748b; font-size:.84rem; line-height:1.5; }
.eg-profile-facts { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.5rem; margin-top:.9rem; }
.eg-fact { padding:.58rem .65rem; background:#f8fbff; border:1px solid #e2e8f0; border-radius:8px; min-width:0; }
.eg-fact span,.eg-fact strong { display:block; overflow-wrap:anywhere; }
.eg-fact span { color:#64748b; font-size:.72rem; }
.eg-fact strong { margin-top:.12rem; color:#334155; font-size:.83rem; font-weight:700; }
.eg-score { padding:1.05rem 1.15rem; background:#f8fbff; border-left:1px solid #e2e8f0; }
.eg-score-row { display:flex; justify-content:space-between; gap:.75rem; padding:.48rem 0; border-bottom:1px solid #e2e8f0; color:#64748b; font-size:.82rem; }
.eg-score-row:last-child { border-bottom:0; }
.eg-score-row strong { color:#1e293b; font-size:.94rem; font-variant-numeric:tabular-nums; }
.eg-subject-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.75rem; }
.eg-subject { min-height:190px; display:flex; flex-direction:column; padding:1rem 1.05rem; background:#fff; border:1px solid #e2e8f0; border-radius:12px; }
.eg-subject-top,.eg-subject-footer { display:flex; justify-content:space-between; align-items:center; gap:.75rem; }
.eg-subject-name { display:flex; align-items:center; gap:.5rem; color:#1e293b; font-weight:700; }
.eg-dot { width:.65rem; height:.65rem; flex:0 0 auto; border-radius:50%; background:var(--eg-accent); }
.eg-status { padding:.18rem .5rem; border:1px solid color-mix(in srgb, var(--eg-accent) 25%, white); border-radius:999px; color:var(--eg-accent); background:var(--eg-soft); font-size:.72rem; white-space:nowrap; }
.eg-subject-copy { margin:.75rem 0; color:#64748b; font-size:.84rem; line-height:1.6; }
.eg-subject-footer { margin-top:auto; color:#475569; font-size:.78rem; }
.eg-math { --eg-accent:#2563eb; --eg-soft:#eff6ff; }
.eg-english { --eg-accent:#008d68; --eg-soft:#ecfdf5; }
.eg-politics { --eg-accent:#b45309; --eg-soft:#fffbeb; }
.eg-major { --eg-accent:#d94801; --eg-soft:#fff7ed; }
.eg-workspace { margin-top:.8rem; padding:1.1rem 1.2rem; background:#fff; border:1px solid #e2e8f0; border-radius:12px; }
.eg-workspace-head { display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; margin-bottom:.85rem; }
.eg-workspace-head h3 { margin:0; color:#1e293b; font-size:1.04rem; }
.eg-workspace-head p { margin:.25rem 0 0; color:#64748b; font-size:.84rem; line-height:1.55; }
.eg-pool-note { padding:.75rem .85rem; border-radius:8px; color:#334155; background:#f8fafc; font-size:.84rem; }
.eg-question-meta { margin:1rem 0 .42rem; color:#475569; font-size:.88rem; }
.eg-question-meta strong { color:#1e293b; font-weight:700; }
.stProgress { margin:0 0 1rem; }
.stProgress > div > div > div > div { height:5px; border-radius:999px; }
div[data-testid="stRadio"] { margin-top:.9rem; }
div[data-testid="stRadio"] label { align-items:flex-start; line-height:1.55; }
.eg-requirement-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.65rem; }
.eg-requirement-card { min-width:0; padding:.72rem .78rem; background:#fbfcff; border:1px solid #e2e8f0; border-radius:8px; }
.eg-requirement-card.is-overflow { background:#fff; }
.eg-requirement-head { display:flex; align-items:flex-start; gap:.55rem; min-width:0; }
.eg-requirement-rank { flex:0 0 auto; min-width:1.65rem; color:#4f46e5; font-size:.72rem; font-weight:800; font-variant-numeric:tabular-nums; }
.eg-requirement-title { min-width:0; color:#1e293b; font-size:.88rem; font-weight:700; overflow-wrap:anywhere; }
.eg-requirement-meta { margin-top:.28rem; color:#64748b; font-size:.74rem; line-height:1.45; }
.eg-requirement-reason { margin:.3rem 0 0; color:#475569; font-size:.79rem; line-height:1.5; }
.eg-requirement-card:not(.is-overflow) .eg-requirement-reason { display:-webkit-box; overflow:hidden; -webkit-box-orient:vertical; -webkit-line-clamp:2; }
.eg-requirement-caption { margin:.65rem 0 .45rem; color:#64748b; font-size:.76rem; }
.eg-requirement-panel { margin-top:.75rem; }
.eg-requirement-panel div[data-testid="stExpander"] { margin-top:.65rem; }
div[data-testid="stExpander"] details { border-color:#e2e8f0; border-radius:8px; background:#fbfcff; }
div[data-testid="stExpander"] summary { color:#4f46e5; font-size:.8rem; font-weight:700; }
div[data-testid="stForm"] { border:1px solid #e2e8f0; border-radius:10px; background:#fff; }
div[data-testid="stButton"] > button { min-height:2.45rem; border-radius:8px; white-space:normal; }
div[data-testid="stMetric"] { padding:.7rem .8rem; border:1px solid #e2e8f0; border-radius:8px; background:#f8fbff; }
@media (max-width: 850px) { .eg-profile { grid-template-columns:1fr; } .eg-score { border-left:0; border-top:1px solid #e2e8f0; } .eg-profile-facts { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media (max-width: 680px) { .block-container { padding-left:.9rem; padding-right:.9rem; } .eg-header { display:block; } .eg-subject-grid { grid-template-columns:1fr; } .eg-title { font-size:1.42rem; } .eg-workspace { padding:1rem; } .eg-requirement-grid { grid-template-columns:1fr; } }

/* Math workspace: same restrained product language as the exam-goal preview. */
.stApp { background:#f1f5f9; }
.eg-math-overview { display:grid; grid-template-columns:minmax(0,1fr) minmax(320px,.82fr); gap:1rem; align-items:stretch; margin:1.1rem 0 .9rem; }
.eg-math-overview-copy, .eg-math-overview-stats { background:#fff; border:1px solid #e2e8f0; border-radius:12px; }
.eg-math-overview-copy { padding:1.25rem 1.35rem; }
.eg-math-kicker { color:#4f46e5; font-size:.74rem; font-weight:700; }
.eg-math-overview-copy h2 { margin:.32rem 0 .25rem; color:#1e293b; font-size:1.22rem; font-weight:700; }
.eg-math-overview-copy p { max-width:58ch; margin:0; color:#64748b; font-size:.84rem; line-height:1.62; }
.eg-math-overview-stats { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.65rem; padding:1rem; background:#f8fbff; }
.eg-math-stat { min-width:0; padding:.7rem .75rem; background:#fff; border:1px solid #e2e8f0; border-radius:8px; }
.eg-math-stat span, .eg-math-stat strong { display:block; overflow-wrap:anywhere; }
.eg-math-stat span { color:#64748b; font-size:.72rem; }
.eg-math-stat strong { margin-top:.16rem; color:#1e293b; font-size:.98rem; font-weight:700; font-variant-numeric:tabular-nums; }
.eg-source-strip { display:flex; justify-content:space-between; align-items:center; gap:1rem; margin:.75rem 0 1rem; padding:.75rem .9rem; color:#475569; background:#fbfcff; border:1px solid #e2e8f0; border-radius:8px; font-size:.82rem; }
.eg-source-strip strong { color:#1e293b; margin-right:.55rem; }
.eg-source-strip span { overflow-wrap:anywhere; }
.eg-source-status { color:#4f46e5; font-weight:700; white-space:nowrap; }
.eg-diagnosis-panel { margin-top:.75rem; padding:1.1rem 1.2rem; background:#fff; border:1px solid #e2e8f0; border-radius:12px; }
.eg-panel-heading { display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; margin-bottom:.85rem; }
.eg-panel-heading h3 { margin:0; color:#1e293b; font-size:1rem; font-weight:700; }
.eg-panel-heading p { margin:.28rem 0 0; color:#64748b; font-size:.82rem; line-height:1.55; }
.eg-panel-count { color:#64748b; font-size:.76rem; white-space:nowrap; }
.eg-empty-state { padding:1rem; background:#f8fafc; border:1px dashed #cbd5e1; border-radius:8px; }
.eg-empty-state h4 { margin:0; color:#334155; font-size:.9rem; }
.eg-empty-state p { margin:.3rem 0 0; color:#64748b; font-size:.82rem; line-height:1.55; }
.eg-question-card { margin-top:.75rem; padding:1rem 1.1rem 1.1rem; background:#fff; border:1px solid #e2e8f0; border-radius:12px; }
.eg-question-meta { margin:0 0 .75rem; padding:.85rem .95rem; color:#64748b; background:#fbfcff; border:1px solid #e2e8f0; border-radius:8px; font-size:.8rem; line-height:1.55; }
.eg-question-meta strong { color:#1e293b; font-weight:700; }
.eg-question-meta span { color:#64748b; }
.eg-knowledge-tags { display:flex; flex-wrap:wrap; gap:.35rem; margin:.35rem 0 .7rem; }
.eg-knowledge-tag { display:inline-block; max-width:100%; padding:.2rem .5rem; color:#334155; background:#f1f5f9; border:1px solid #dbe3ec; border-radius:999px; font-size:.74rem; line-height:1.35; overflow-wrap:anywhere; }
.eg-knowledge-catalog { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.15rem .65rem; margin-top:.65rem; }
.eg-knowledge-catalog-item { display:flex; min-width:0; align-items:baseline; gap:.42rem; padding:.35rem .4rem; border-bottom:1px solid #edf2f7; color:#475569; font-size:.76rem; line-height:1.4; }
.eg-knowledge-catalog-index { flex:0 0 2rem; color:#94a3b8; font-size:.68rem; font-variant-numeric:tabular-nums; }
.eg-knowledge-catalog-label { min-width:0; overflow-wrap:anywhere; }
.eg-question-label { margin:.8rem 0 .28rem; color:#94a3b8; font-size:.72rem; font-weight:700; }
.eg-question-card .stProgress, div[data-testid="stProgress"] { margin:.2rem 0 .9rem; }
.eg-question-card .stProgress > div > div > div > div, div[data-testid="stProgress"] > div > div > div > div { height:5px; border-radius:999px; }
div[class*="st-key-math_pool_answer_"] div[data-testid="stRadio"] { margin-top:.3rem; padding:0; background:transparent; border:0; border-radius:0; }
div[class*="st-key-math_pool_answer_"] div[data-testid="stRadio"] > label { margin:0 0 .42rem; padding:0 !important; background:transparent !important; border:0 !important; border-radius:0 !important; }
div[class*="st-key-math_pool_answer_"] div[data-testid="stRadio"] > div[role="radiogroup"] { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.55rem .7rem; }
div[class*="st-key-math_pool_answer_"] div[data-testid="stRadio"] > div[role="radiogroup"] > label { min-width:0; margin:0 !important; padding:.58rem .68rem !important; background:transparent !important; border:1px solid #dbe3ec !important; border-radius:8px !important; box-sizing:border-box; align-items:flex-start !important; line-height:1.45 !important; }
div[class*="st-key-math_pool_answer_"] div[data-testid="stRadio"] > div[role="radiogroup"] > label:hover { background:#f8fafc !important; border-color:#cbd5e1 !important; }
div[class*="st-key-math_pool_answer_"] div[data-testid="stRadio"] > div[role="radiogroup"] > label:focus-within { border-color:#93c5fd !important; box-shadow:0 0 0 2px rgba(37,99,235,.12); }
div[class*="st-key-math_pool_answer_"] div[data-testid="stRadio"] > div[role="radiogroup"] > label:has(input:checked) { background:#eff6ff !important; border-color:#93c5fd !important; }
div[class*="st-key-math_pool_answer_"] div[data-testid="stRadio"] > div[role="radiogroup"] > label [data-testid="stMarkdownContainer"] { min-width:0; overflow-wrap:anywhere; }
@media (max-width: 560px) { div[class*="st-key-math_pool_answer_"] div[data-testid="stRadio"] > div[role="radiogroup"] { grid-template-columns:1fr; } }
@media (max-width: 780px) { .eg-knowledge-catalog { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media (max-width: 500px) { .eg-knowledge-catalog { grid-template-columns:1fr; } }
.eg-question-card div[data-testid="stTextArea"] textarea, div[data-testid="stTextArea"] textarea { background:#fff; border-color:#cbd5e1; }
.eg-question-card div[data-testid="stSelectbox"], div[data-testid="stSelectbox"] { margin-top:.65rem; }
.eg-question-card .stButton > button { width:100%; }
.eg-requirements-panel, .eg-training-panel { margin-top:1rem; padding:1.1rem 1.2rem; background:#fff; border:1px solid #e2e8f0; border-radius:12px; }
.eg-requirements-panel > h3, .eg-training-panel > h3 { margin:0; color:#1e293b; font-size:1rem; font-weight:700; }
.eg-requirements-panel > p, .eg-training-panel > p { margin:.28rem 0 .8rem; color:#64748b; font-size:.82rem; line-height:1.55; }
.eg-requirements-panel div[data-baseweb="tab-list"] { gap:.3rem; }
.eg-requirements-panel button[role="tab"] { min-height:2.25rem; padding:0 .8rem; border-radius:8px 8px 0 0; color:#64748b; font-size:.8rem; }
.eg-requirements-panel button[role="tab"][aria-selected="true"] { color:#4f46e5; font-weight:700; }
.eg-training-select { margin-top:.75rem; }
div.st-key-start_math_pool_diagnosis, div.st-key-restart_math_pool_diagnosis { margin-top:.75rem; }
div.st-key-start_math_pool_diagnosis > button { min-height:2.55rem; }
@media (max-width: 850px) { .eg-math-overview { grid-template-columns:1fr; } }
@media (max-width: 680px) { .eg-math-overview-stats { grid-template-columns:1fr 1fr; } .eg-source-strip { align-items:flex-start; flex-direction:column; gap:.35rem; } .eg-diagnosis-panel, .eg-question-card, .eg-requirements-panel, .eg-training-panel { padding:.95rem; } .eg-panel-heading { display:block; } .eg-panel-count { display:block; margin-top:.35rem; } }
</style>
        """,
        unsafe_allow_html=True,
    )

def _ordered_requirements_for_display(requirements):
    tier_order = {"基础": 0, "标准": 1, "提高": 2}
    return tuple(
        sorted(
            requirements,
            key=lambda item: (
                -float(getattr(item, "priority", 0.0)),
                tier_order.get(str(getattr(item, "tier", "")), 99),
                str(getattr(item, "knowledge_point_id", "")),
            ),
        )
    )


def _requirement_item_markup(requirement, rank, compact=True):
    requirement_class = "eg-requirement-card" if compact else "eg-requirement-card is-overflow"
    knowledge_label = html.escape(_knowledge_label(requirement.knowledge_point_id))
    reason = html.escape(str(requirement.reason or ""))
    tier = html.escape(str(getattr(requirement, "tier", "")))
    priority = float(getattr(requirement, "priority", 0.0))
    return f"""
<div class="{requirement_class}">
  <div class="eg-requirement-head"><span class="eg-requirement-rank">{rank:02d}</span><div class="eg-requirement-title">{knowledge_label}</div></div>
  <div class="eg-requirement-meta">当前 {requirement.mastery:.0%} · 目标 {requirement.target_mastery:.0%} · {tier} · 优先级 {priority:.2f}</div>
  <p class="eg-requirement-reason">{reason}</p>
</div>
"""


def _render_requirement_item(st, requirement, compact=True, rank=1):
    st.markdown(
        _requirement_item_markup(requirement, rank, compact=compact),
        unsafe_allow_html=True,
    )


def _render_requirement_grid(st, requirements, start_rank=1, compact=True):
    markup = "<div class=\"eg-requirement-grid\">" + "".join(
        _requirement_item_markup(requirement, start_rank + index, compact=compact)
        for index, requirement in enumerate(requirements)
    ) + "</div>"
    st.markdown(markup, unsafe_allow_html=True)


def _render_requirement_group(st, requirements, visible_limit=6):
    if not requirements:
        st.caption("当前没有需要优先处理的知识点。")
        return
    ordered = _ordered_requirements_for_display(requirements)
    visible = ordered[:visible_limit]
    if hasattr(st, "expander"):
        _render_requirement_grid(st, visible, start_rank=1)
    else:
        for index, requirement in enumerate(visible, start=1):
            _render_requirement_item(st, requirement, rank=index)
    hidden = ordered[visible_limit:]
    if hidden and hasattr(st, "expander"):
        st.caption(f"已按优先级展示前 {len(visible)} 项，其余 {len(hidden)} 项收在下方。")
        with st.expander(f"查看全部 {len(ordered)} 项", expanded=False):
            _render_requirement_grid(st, hidden, start_rank=len(visible) + 1, compact=False)
    elif hidden:
        for index, requirement in enumerate(hidden, start=len(visible) + 1):
            _render_requirement_item(st, requirement, compact=False, rank=index)


def _training_requirement_labels(requirements):
    """Create stable, ranked labels so the selectbox exposes the actual priority order."""
    return tuple(
        f"{index:02d} · {_knowledge_label(item.knowledge_point_id)} · {item.tier} · 优先级 {item.priority:.2f}"
        for index, item in enumerate(_ordered_requirements_for_display(requirements), start=1)
    )


def _render_subject_overview(st, profile, diagnosis_count, pool_count):
    goal = f"{profile.target_score:.0f} 分" if profile else "待设置"
    current = f"{profile.current_score:.0f} 分" if profile else "待设置"
    st.markdown(
        f"""
<div class="eg-subject-grid">
  <section class="eg-subject eg-math">
    <div class="eg-subject-top"><div class="eg-subject-name"><i class="eg-dot"></i>数学</div><span class="eg-status">分析已开启</span></div>
    <p class="eg-subject-copy">目标 {goal}，当前基线 {current}。已确认题库 {pool_count} 题，诊断记录 {diagnosis_count} 题。</p>
    <div class="eg-subject-footer"><span>真题映射后可直接复用诊断</span><span>↓ 数学工作区</span></div>
  </section>
  <section class="eg-subject eg-english">
    <div class="eg-subject-top"><div class="eg-subject-name"><i class="eg-dot"></i>英语</div><span class="eg-status">接口已预留</span></div>
    <p class="eg-subject-copy">后续记录目标分、真题表现和阅读、写作、词汇等分项证据，不套用数学规则。</p>
    <div class="eg-subject-footer"><span>从最近一次真题开始</span><span>待接入</span></div>
  </section>
  <section class="eg-subject eg-politics">
    <div class="eg-subject-top"><div class="eg-subject-name"><i class="eg-dot"></i>政治</div><span class="eg-status">接口已预留</span></div>
    <p class="eg-subject-copy">将围绕章节、自评、选择题与主观题材料建立自己的复习策略。</p>
    <div class="eg-subject-footer"><span>保留独立数据模型</span><span>待接入</span></div>
  </section>
  <section class="eg-subject eg-major">
    <div class="eg-subject-top"><div class="eg-subject-name"><i class="eg-dot"></i>专业课</div><span class="eg-status">独立维护</span></div>
    <p class="eg-subject-copy">保留院校考试范围、参考书、真题和个人资料；不接入公共课加权算法。</p>
    <div class="eg-subject-footer"><span>院校与专业只作备考记录</span><span>待完善</span></div>
  </section>
</div>
        """,
        unsafe_allow_html=True,
    )


def _render_subject_overview_aligned(st, profile, diagnosis_count, pool_count):
    goal = f"{profile.target_score:.0f} 分" if profile else "待设置"
    current = f"{profile.current_score:.0f} 分" if profile else "待设置"
    math_markup = f"""
<section class="eg-subject eg-math">
  <div class="eg-subject-top"><div class="eg-subject-name"><i class="eg-dot"></i>数学</div><span class="eg-status">分析已开启</span></div>
  <p class="eg-subject-copy">目标 {goal}，当前基线 {current}。已确认题库 {pool_count} 题，诊断记录 {diagnosis_count} 题。</p>
  <div class="eg-subject-footer"><span>真题映射后可直接复用诊断</span><span>数学工作区</span></div>
</section>
"""
    english_markup = """
<section class="eg-subject eg-english">
  <div class="eg-subject-top"><div class="eg-subject-name"><i class="eg-dot"></i>英语</div><span class="eg-status">接口已预留</span></div>
  <p class="eg-subject-copy">后续记录目标分、真题表现和阅读、写作、词汇等分项证据，不套用数学规则。</p>
  <div class="eg-subject-footer"><span>从最近一次真题开始</span><span>待接入</span></div>
</section>
"""
    politics_markup = """
<section class="eg-subject eg-politics">
  <div class="eg-subject-top"><div class="eg-subject-name"><i class="eg-dot"></i>政治</div><span class="eg-status">接口已预留</span></div>
  <p class="eg-subject-copy">将围绕章节、自评、选择题与主观题材料建立自己的复习策略。</p>
  <div class="eg-subject-footer"><span>保留独立数据模型</span><span>待接入</span></div>
</section>
"""
    major_markup = """
<section class="eg-subject eg-major">
  <div class="eg-subject-top"><div class="eg-subject-name"><i class="eg-dot"></i>专业课</div><span class="eg-status">独立维护</span></div>
  <p class="eg-subject-copy">保留院校考试范围、参考书、真题和个人资料，不接入公共课加权算法。</p>
  <div class="eg-subject-footer"><span>院校与专业只作备考记录</span><span>待完善</span></div>
</section>
"""

    math_column, english_column = st.columns(2)
    with math_column:
        st.markdown(math_markup, unsafe_allow_html=True)
        math_clicked = st.button("进入数学学习策略", type="primary", key="enter_math_goal_workspace")
    with english_column:
        st.markdown(english_markup, unsafe_allow_html=True)

    politics_column, major_column = st.columns(2)
    with politics_column:
        st.markdown(politics_markup, unsafe_allow_html=True)
    with major_column:
        st.markdown(major_markup, unsafe_allow_html=True)
    return math_clicked


def split_question_content(question_text: str):
    """Separate a choice stem from inline or line-separated answer options."""
    matches = list(re.finditer(r"(?<![A-Za-z])([A-E])\s*[).、]\s*", question_text or ""))
    if len(matches) < 2:
        return str(question_text or "").strip(), {}
    stem = question_text[:matches[0].start()].strip()
    options = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(question_text)
        options[match.group(1).upper()] = question_text[match.end():end].strip()
    return stem, options


def _knowledge_label(knowledge_point_id: str) -> str:
    return re.sub(r"^\d{3}-|\.md$", "", str(knowledge_point_id or "")).strip()


def format_knowledge_point_tags(knowledge_point_ids: Iterable[str]):
    return tuple(
        _knowledge_label(value)
        for value in dict.fromkeys(str(value).strip() for value in knowledge_point_ids if str(value).strip())
    )


def format_knowledge_catalog_markup(knowledge_points: Iterable[Mapping[str, str]]):
    """Render the full catalog as a compact, readable directory instead of a paragraph."""
    items = []
    for index, point in enumerate(knowledge_points, start=1):
        knowledge_id = str(point.get("id") or "").strip()
        if not knowledge_id:
            continue
        label = html.escape(_knowledge_label(knowledge_id))
        number = html.escape(knowledge_id.split("-", 1)[0] if "-" in knowledge_id else f"{index:03d}")
        items.append(
            f'<div class="eg-knowledge-catalog-item"><span class="eg-knowledge-catalog-index">{number}</span>'
            f'<span class="eg-knowledge-catalog-label">{label}</span></div>'
        )
    return '<div class="eg-knowledge-catalog">' + "".join(items) + "</div>"


def format_question_metadata(year, difficulty_tier, mapping_status, knowledge_point_ids, source_reference=""):
    source = f"{year} 年真题" if classify_question_source(source_reference, mapping_status) == "true_exam" else "真题变式（非真题）"
    return {
        "source": source,
        "difficulty": str(difficulty_tier),
        "knowledge_point_labels": format_knowledge_point_tags(knowledge_point_ids),
        "knowledge_points": "、".join(_knowledge_label(value) for value in knowledge_point_ids),
    }


def _render_math_workspace(st, connection, user_key, profile, knowledge_points, generate_training_material, generate_diagnosis_variants, generate_diagnosis_summary, render_generation_progress):
    evidence = list_evidence(connection, user_key, profile.exam_type)
    mastery = calculate_mastery(evidence)
    session_id = st.session_state.get("math_diagnosis_session_id", "")
    diagnosis_complete = has_completed_diagnosis(evidence, session_id=session_id) if session_id else has_completed_diagnosis(evidence)
    confirmed_questions = list_eligible_exam_questions(connection, profile.exam_type)
    diagnostic_pool = list_diagnostic_questions(connection, profile.exam_type)
    catalog_knowledge_ids = tuple(dict.fromkeys(
        str(point.get("id") or "").strip()
        for point in knowledge_points
        if str(point.get("id") or "").strip()
    ))
    mapped_knowledge_ids = {
        knowledge_id
        for question in diagnostic_pool
        for knowledge_id in question.knowledge_point_ids
    }
    mapped_catalog_count = len(mapped_knowledge_ids.intersection(catalog_knowledge_ids))
    summary = (
        build_requirements(
            profile,
            mastery,
            confirmed_questions,
            knowledge_point_ids=tuple(point.get("id", "") for point in knowledge_points),
        )
        if diagnosis_complete and confirmed_questions
        else build_diagnostic_requirements(profile, mastery, [point["id"] for point in knowledge_points])
        if diagnosis_complete
        else None
    )
    true_exam_questions = [question for question in diagnostic_pool if question.is_true_exam]
    variant_questions = [question for question in diagnostic_pool if not question.is_true_exam]
    diagnosis_count = count_diagnosis_questions(evidence, session_id=session_id) if session_id else count_diagnosis_questions(evidence)
    remaining_diagnosis = max(0, 20 - diagnosis_count)
    exam_label = next((label for label, value in EXAM_TYPES.items() if value == profile.exam_type), profile.exam_type)
    st.markdown(
        f'''
<section class="eg-math-overview" data-layout-version="preview-v2">
  <div class="eg-math-overview-copy">
    <span class="eg-math-kicker">数学学习策略 · {html.escape(exam_label)}</span>
    <h2>把每次作答变成下一步复习依据</h2>
    <p>诊断题优先来自当前版本真题和对应变式。系统会结合题目分值、难度、知识点覆盖与作答记录，持续调整你的掌握要求。</p>
  </div>
  <div class="eg-math-overview-stats" aria-label="数学学习概览">
    <div class="eg-math-stat"><span>目标 / 当前</span><strong>{profile.target_score:.0f} / {profile.current_score:.0f}</strong></div>
    <div class="eg-math-stat"><span>诊断进度</span><strong>{diagnosis_count} / 20</strong></div>
    <div class="eg-math-stat"><span>可用题库</span><strong>{len(diagnostic_pool)} 题</strong></div>
    <div class="eg-math-stat"><span>当前模式</span><strong>{'巩固与冲刺' if profile.is_above_target else '补齐目标差距'}</strong></div>
  </div>
</section>
<div class="eg-source-strip"><div><strong>题库组成</strong><span>截图真题 {len(true_exam_questions)} 题 · AI 真题变式 {len(variant_questions)} 题</span></div><span class="eg-source-status">{('可开始诊断' if diagnostic_pool else '等待导入题目')}</span></div>
<div class="eg-diagnosis-panel"><div class="eg-panel-heading"><div><h3>本阶段分层诊断</h3><p>一次完成 20 题，答题后会更新知识点掌握度与下一阶段优先级。</p></div><span class="eg-panel-count">剩余 {remaining_diagnosis} 题</span></div></div>
        ''',
        unsafe_allow_html=True,
    )
    active_questions = st.session_state.get("math_diagnosis_questions")
    if not active_questions:
        if not diagnostic_pool:
            st.markdown(
                '<div class="eg-empty-state"><h4>诊断题库还没有可用题目</h4><p>先导入至少一道已确认真题，才能建立可追溯的诊断题库。</p></div>',
                unsafe_allow_html=True,
            )
        elif st.button("开始本阶段复诊（20 题）", type="primary", key="start_math_pool_diagnosis"):
            plan = build_diagnosis_plan(choose_diagnosis_knowledge_points(knowledge_points, mastery, 20), 20)
            selection = select_diagnosis_questions(
                plan,
                diagnostic_pool,
                allowed_mapping_statuses=("confirmed", "ai_suggested"),
                true_question_ratio=0.6,
                coverage_knowledge_point_ids=catalog_knowledge_ids,
            )
            reference_questions = [question for question in diagnostic_pool if question.is_true_exam and question.knowledge_point_ids]
            missing = diagnosis_generation_slots(plan, selection, true_question_ratio=0.6)
            if missing and generate_diagnosis_variants and reference_questions:
                progress = st.empty()
                try:
                    if render_generation_progress:
                        render_generation_progress(progress, "request_started")
                    variants = build_variant_questions(generate_diagnosis_variants(build_variant_batch_prompt(missing, reference_questions)), missing, reference_questions)
                    if variants:
                        import_exam_questions(connection, variants, data_version="generated-v1")
                        selection = select_diagnosis_questions(
                            plan,
                            list_diagnostic_questions(connection, profile.exam_type),
                            allowed_mapping_statuses=("confirmed", "ai_suggested"),
                            true_question_ratio=0.6,
                            coverage_knowledge_point_ids=catalog_knowledge_ids,
                        )
                    if render_generation_progress:
                        render_generation_progress(progress, "completed")
                except Exception as error:
                    st.warning(f"真题变式补题未完成：{error}")
                finally:
                    progress.empty()
            st.session_state.math_diagnosis_questions = selection.questions
            st.session_state.math_diagnosis_index = 0
            st.session_state.math_diagnosis_uncovered = selection.uncovered_plan_indexes
            st.session_state.math_diagnosis_uncovered_knowledge = selection.uncovered_knowledge_point_ids
            st.session_state.math_diagnosis_session_id = uuid4().hex
            st.rerun()
    else:
        index = int(st.session_state.get("math_diagnosis_index", 0))
        if index >= len(active_questions):
            st.success("本阶段复诊完成，掌握要求已更新。")
            session_id = st.session_state.get("math_diagnosis_session_id", "")
            session_source = f"diagnosis:{session_id}" if session_id else "diagnosis"
            session_evidence = [item for item in evidence if item.source == session_source]
            report = build_diagnosis_report(profile, diagnostic_pool, session_evidence)
            if report:
                st.markdown('<h2 class="eg-section-title">加权诊断结论</h2>', unsafe_allow_html=True)
                st.caption("已综合每题分值、难度、题源和你的主观反馈；LLM 只解释下方的加权证据。")
                report_key = tuple((item.knowledge_point_id, round(item.weakness_score, 3)) for item in report)
                if generate_diagnosis_summary and st.session_state.get("math_diagnosis_summary_key") != report_key:
                    try:
                        with st.spinner("正在整理你的薄弱点..."):
                            st.session_state.math_diagnosis_summary = generate_diagnosis_summary(
                                build_diagnosis_summary_prompt(profile, report)
                            )
                            st.session_state.math_diagnosis_summary_key = report_key
                    except Exception as error:
                        st.warning(f"加权结果已生成，但 AI 总结暂时不可用：{error}")
                if st.session_state.get("math_diagnosis_summary"):
                    st.markdown(st.session_state.math_diagnosis_summary)
            if st.button("以后再发起下一阶段复诊", key="restart_math_pool_diagnosis"):
                for key in ("math_diagnosis_questions", "math_diagnosis_index", "math_diagnosis_uncovered", "math_diagnosis_uncovered_knowledge", "math_diagnosis_session_id", "math_diagnosis_summary", "math_diagnosis_summary_key"):
                    st.session_state.pop(key, None)
                st.rerun()
        else:
            question = active_questions[index]
            uncovered_knowledge = tuple(st.session_state.get("math_diagnosis_uncovered_knowledge", ()))
            if uncovered_knowledge and index == 0:
                st.info(
                    f"本轮已按题库标签最大化覆盖 20 题，仍有 {len(uncovered_knowledge)} 个知识点暂无可追溯题目；"
                    "系统不会把未考察的知识点硬贴到题目上。"
                )
            metadata = format_question_metadata(question.year, question.difficulty_tier, question.mapping_status, question.knowledge_point_ids, question.source_reference)
            knowledge_tags = "".join(
                f'<span class="eg-knowledge-tag">{html.escape(label)}</span>'
                for label in metadata["knowledge_point_labels"]
            )
            st.markdown(
                f'<div class="eg-question-meta"><strong>第 {index + 1} / {len(active_questions)} 题</strong> · '
                f'<strong>{html.escape(metadata["source"])} · {html.escape(metadata["difficulty"])}题</strong></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="eg-knowledge-tags">{knowledge_tags}</div>',
                unsafe_allow_html=True,
            )
            st.progress((index + 1) / len(active_questions))
            st.markdown('<div class="eg-question-label">题目</div>', unsafe_allow_html=True)
            stem, options = split_question_content(question.question_text)
            st.markdown(stem)
            st.markdown('<div class="eg-question-label">你的作答</div>', unsafe_allow_html=True)
            answer = st.radio(
                "选择答案",
                list(options),
                format_func=lambda option: f"{option}. {options[option]}",
                key=f"math_pool_answer_{question.question_id}",
            ) if options else st.text_area("你的答案", key=f"math_pool_answer_{question.question_id}")
            feedback = st.selectbox(
                "这题对你的感受",
                ("正常", "偏简单", "偏难", "知识点遗漏"),
                key=f"math_pool_feedback_{question.question_id}",
            )
            if st.button("提交本题", type="primary", key=f"submit_math_pool_{question.question_id}"):
                is_correct = is_math_answer_correct(question, answer)
                if is_correct is None:
                    st.warning("这道题的答案格式无法可靠自动判断，请按参考答案格式作答后再提交。")
                    return
                error_type = f"{'诊断答错；' if not is_correct else ''}反馈: {feedback}"
                for item in record_diagnosis_answer(
                    user_key, question.question_id, question.knowledge_point_ids, is_correct,
                    question.difficulty_coefficient, error_type,
                    session_id=st.session_state.get("math_diagnosis_session_id", ""),
                    exam_type=profile.exam_type,
                ):
                    save_evidence(connection, item)
                st.session_state.math_diagnosis_index = index + 1
                st.rerun()
    st.markdown(
        '<div class="eg-requirements-panel"><h3>掌握要求</h3><p>完成本阶段诊断后，系统会按加权证据分为必须掌握、应该掌握和冲刺掌握。</p></div>',
        unsafe_allow_html=True,
    )
    if summary is None:
        remaining = max(0, 20 - count_diagnosis_questions(evidence, session_id=session_id)) if session_id else 20
        st.info(f"完成本轮 20 题诊断后，系统才会根据你的作答生成必须掌握、应该掌握和冲刺掌握。还差 {remaining} 题。")
    else:
        tabs = st.tabs(["必须掌握", "应该掌握", "冲刺掌握"])
        for tab, requirements in zip(tabs, (summary.must, summary.should, summary.stretch)):
            with tab:
                _render_requirement_group(st, requirements)
    with st.expander(f"完整数学知识点（{len(knowledge_points)} 个）", expanded=False):
        st.caption("未被当前题库覆盖的知识点会保留在目录中，状态为待诊断，不会从知识库消失。")
        st.caption(f"当前题库已映射 {mapped_catalog_count} / {len(catalog_knowledge_ids)} 个知识点")
        st.markdown(format_knowledge_catalog_markup(knowledge_points), unsafe_allow_html=True)
    st.markdown(
        '<div class="eg-training-panel"><h3>强化训练</h3><p>把当前优先级转成针对性的学习资料，生成内容不会替代真题和题库证据。</p></div>',
        unsafe_allow_html=True,
    )
    requirement_groups = (
        ("必须掌握", _ordered_requirements_for_display(summary.must if summary else ())),
        ("应该掌握", _ordered_requirements_for_display(summary.should if summary else ())),
        ("冲刺掌握", _ordered_requirements_for_display(summary.stretch if summary else ())),
    )
    available_groups = tuple((label, values) for label, values in requirement_groups if values)
    if not available_groups:
        st.info("完成诊断后可在这里生成针对性的强化资料。")
        return
    selected_group_label = st.radio(
        "强化范围",
        [label for label, _ in available_groups],
        horizontal=True,
        key="math_training_tier",
    )
    selected_group = dict(available_groups)[selected_group_label]
    labels = list(_training_requirement_labels(selected_group))
    selected_label = st.selectbox("选择强化知识点", labels, key="math_training_requirement")
    selected = selected_group[labels.index(selected_label)]
    if st.button("生成强化资料", type="primary", key="generate_math_training_material") and generate_training_material:
        request = build_training_material_request(selected)
        text = next((point.get("text", "") for point in knowledge_points if point.get("id") == request.knowledge_point_id), "")
        st.session_state.math_training_material = generate_training_material(build_training_material_prompt(request, text))
    if st.session_state.get("math_training_material"):
        st.markdown(st.session_state.math_training_material)


def render_math_personalization_page(
    st,
    connection,
    user_id,
    knowledge_points: Sequence[Mapping[str, str]],
    generate_review_questions=None,
    generate_training_material=None,
    generate_diagnosis_variants=None,
    generate_diagnosis_summary=None,
    render_generation_progress=None,
):
    """Render the goal overview and the local, reusable math diagnosis workflow."""
    del generate_review_questions
    ensure_schema(connection)
    repaired = repair_legacy_question_mapping_ids(
        connection,
        tuple(point.get("id", "") for point in knowledge_points),
    )
    if repaired:
        for key in ("math_diagnosis_questions", "math_diagnosis_index", "math_diagnosis_uncovered", "math_diagnosis_uncovered_knowledge"):
            st.session_state.pop(key, None)
    user_key = str(user_id)
    profile = get_profile(connection, user_key)
    evidence = list_evidence(connection, user_key, profile.exam_type if profile else None)
    mastery = calculate_mastery(evidence)
    diagnosis_count = count_diagnosis_questions(evidence)
    exam_questions = list_eligible_exam_questions(connection, profile.exam_type) if profile else []
    diagnostic_questions = list_diagnostic_questions(connection, profile.exam_type) if profile else []
    _inject_exam_goal_styles(st)

    st.markdown(
        """
<header class="eg-header">
  <div><h1 class="eg-title">我的备考目标</h1><p class="eg-subtitle">把目标、真题证据和每次练习收在同一个备考档案里。数学先接入个性化掌握要求，英语、政治与专业课保留独立扩展入口。</p></div>
</header>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.get("exam_goal_active_subject") == "math":
        if st.button("← 返回我的备考目标", key="back_to_exam_goal"):
            st.session_state.pop("exam_goal_active_subject", None)
            st.rerun()
        if profile is None:
            st.info("请先回到备考目标建立数学目标。")
            return
        _render_math_workspace(
            st, connection, user_key, profile, knowledge_points,
            generate_training_material, generate_diagnosis_variants, generate_diagnosis_summary, render_generation_progress,
        )
        return

    if profile:
        st.markdown(
            f"""
<section class="eg-profile">
  <div class="eg-profile-main"><div class="eg-profile-top"><div><h2 class="eg-profile-name">备考档案</h2><p class="eg-profile-copy">目标分用于决定学习策略；真实的题目记录持续校正每个知识点的掌握要求。</p></div></div>
    <div class="eg-profile-facts"><div class="eg-fact"><span>目标院校</span><strong>{profile.target_school or '待填写'}</strong></div><div class="eg-fact"><span>目标专业</span><strong>{profile.target_major or '待填写'}</strong></div><div class="eg-fact"><span>本科专业</span><strong>{profile.undergraduate_major or '待填写'}</strong></div><div class="eg-fact"><span>当前阶段</span><strong>{profile.current_stage} · {'跨考' if profile.is_cross_exam else '非跨考'}</strong></div></div>
  </div>
  <aside class="eg-score"><div class="eg-score-row"><span>数学目标</span><strong>{profile.target_score:.0f} / 150</strong></div><div class="eg-score-row"><span>当前基线</span><strong>{profile.current_score:.0f} / 150</strong></div><div class="eg-score-row"><span>当前模式</span><strong>{'巩固与冲刺' if profile.is_above_target else '补齐目标差距'}</strong></div></aside>
</section>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info("先建立数学目标，系统才会生成属于你的诊断计划和掌握要求。")

    with st.expander("编辑备考档案", expanded=profile is None):
        with st.form("math_personalization_profile"):
            current_exam = next((label for label, value in EXAM_TYPES.items() if profile and profile.exam_type == value), "数学一")
            if profile is None:
                default_exam_type = resolve_math_exam_type(connection, user_key)
                current_exam = next(
                    (label for label, value in EXAM_TYPES.items() if value == default_exam_type),
                    current_exam,
                )
            form_left, form_right, form_source = st.columns(3)
            with form_left:
                exam_label = st.selectbox("数学版本", list(EXAM_TYPES), index=list(EXAM_TYPES).index(current_exam))
            with form_right:
                target_score = st.number_input("目标数学分", 0.0, 150.0, float(profile.target_score if profile else 100), 1.0)
            with form_source:
                current_score = st.number_input("当前数学分", 0.0, 150.0, float(profile.current_score if profile else 40), 1.0)
            sources = {"自填": "self_reported", "模考": "mock", "系统诊断": "diagnostic"}
            selected_source = next((label for label, value in sources.items() if profile and profile.score_source == value), "自填")
            score_source = st.selectbox("当前分来源", list(sources), index=list(sources).index(selected_source))
            target_school = st.text_input("目标院校", value=profile.target_school if profile else "")
            target_major = st.text_input("目标专业", value=profile.target_major if profile else "")
            undergrad_major, cross_exam, stage = st.columns(3)
            with undergrad_major:
                undergraduate_major = st.text_input("本科专业", value=profile.undergraduate_major if profile else "")
            with cross_exam:
                is_cross_exam = st.checkbox("是否跨考", value=bool(profile.is_cross_exam) if profile else False)
            with stage:
                stages = ["基础阶段", "强化阶段", "冲刺阶段"]
                current_stage = st.selectbox("当前阶段", stages, index=stages.index(profile.current_stage) if profile and profile.current_stage in stages else 0)
            if st.form_submit_button("保存备考档案", type="primary"):
                new_profile = StudentProfile(user_key, "math", EXAM_TYPES[exam_label], target_score, current_score, sources[score_source], target_school, target_major, undergraduate_major, is_cross_exam, current_stage)
                save_profile(connection, new_profile)
                if not profile or profile.exam_type != new_profile.exam_type:
                    for key in ("math_diagnosis_plan", "math_diagnosis_questions", "math_diagnosis_index", "math_diagnosis_uncovered_knowledge"):
                        st.session_state.pop(key, None)
                st.success("数学目标已保存。")
                st.rerun()

    profile = get_profile(connection, user_key)
    evidence = list_evidence(connection, user_key, profile.exam_type if profile else None)
    mastery = calculate_mastery(evidence)
    diagnosis_count = count_diagnosis_questions(evidence)
    exam_questions = list_eligible_exam_questions(connection, profile.exam_type) if profile else []
    diagnostic_questions = list_diagnostic_questions(connection, profile.exam_type) if profile else []

    st.markdown('<h2 class="eg-section-title">四科备考状态</h2>', unsafe_allow_html=True)
    math_strategy_clicked = _render_subject_overview_aligned(
        st, profile, diagnosis_count, len(diagnostic_questions)
    )
    if profile is None:
        return
    if math_strategy_clicked:
        st.session_state.exam_goal_active_subject = "math"
        st.rerun()
    return
