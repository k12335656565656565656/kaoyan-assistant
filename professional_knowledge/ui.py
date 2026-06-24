"""Streamlit integration wrapper for the professional knowledge system."""

from __future__ import annotations

import streamlit as st

from knowledge_base import ensure_db, render_knowledge_page


def inject_professional_knowledge_styles() -> None:
    """Inject responsive styles shared by standalone and host-app modes."""

    st.markdown(
        """
<style>
    :root {
        --pk-accent: #2f6fed;
        --pk-accent-soft: #eef4ff;
        --pk-ink: #111827;
        --pk-subtle: #667085;
        --pk-muted: #98a2b3;
        --pk-line: #d7dee8;
        --pk-surface: rgba(255, 255, 255, 0.92);
        --pk-surface-strong: #ffffff;
        --pk-panel: rgba(248, 250, 252, 0.88);
        --pk-shadow: 0 12px 40px rgba(15, 23, 42, 0.06);
        --pk-radius: 18px;
        --pk-radius-sm: 12px;
        --pk-warm: #f4f6f8;
        --pk-good: #067647;
        --pk-good-soft: #ecfdf3;
        --pk-warn: #b54708;
        --pk-warn-soft: #fff7ed;
    }
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(229, 239, 255, 0.9), transparent 32%),
            radial-gradient(circle at top right, rgba(244, 246, 248, 0.95), transparent 28%),
            linear-gradient(180deg, #f6f8fb 0%, #f1f4f8 100%);
    }
    .block-container {
        max-width: 1180px;
        padding-top: 1.15rem;
        padding-bottom: 2.8rem;
    }
    .main-title {
        background:
            linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(247, 249, 252, 0.88)),
            linear-gradient(135deg, rgba(47, 111, 237, 0.08), rgba(255, 255, 255, 0));
        border: 1px solid rgba(215, 222, 232, 0.92);
        box-shadow: var(--pk-shadow);
        backdrop-filter: blur(18px);
        border-radius: 24px;
        padding: 1.35rem 1.45rem;
        color: var(--pk-ink);
        text-align: left;
        margin-bottom: 0.95rem;
        position: relative;
        overflow: hidden;
    }
    .main-title::after {
        content: "";
        position: absolute;
        inset: auto -8% -58% auto;
        width: 220px;
        height: 220px;
        background: radial-gradient(circle, rgba(47, 111, 237, 0.16), rgba(47, 111, 237, 0));
        pointer-events: none;
    }
    .main-title h1 {
        font-size: 1.7rem;
        font-weight: 700;
        margin: 0;
        color: var(--pk-ink);
        letter-spacing: -0.02em;
    }
    .main-title p {
        color: var(--pk-subtle);
        margin: 0.34rem 0 0;
        font-size: 0.97rem;
        max-width: 720px;
        line-height: 1.55;
    }
    .pk-kicker {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.22rem 0.62rem;
        border-radius: 999px;
        background: var(--pk-accent-soft);
        color: var(--pk-accent);
        font-size: 0.73rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        margin-bottom: 0.55rem;
    }
    .pk-stage-strip {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.75rem;
        margin: 0.25rem 0 1rem;
    }
    .pk-stage-card {
        background: rgba(255, 255, 255, 0.78);
        border: 1px solid rgba(215, 222, 232, 0.88);
        border-radius: var(--pk-radius);
        padding: 0.95rem 1rem;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
    }
    .pk-stage-card.active {
        border-color: rgba(47, 111, 237, 0.28);
        background: linear-gradient(135deg, rgba(238, 244, 255, 0.95), rgba(255, 255, 255, 0.95));
    }
    .pk-stage-card h3 {
        margin: 0;
        color: var(--pk-ink);
        font-size: 0.98rem;
        font-weight: 650;
        letter-spacing: -0.01em;
    }
    .pk-stage-card p {
        margin: 0.32rem 0 0;
        color: var(--pk-subtle);
        font-size: 0.84rem;
        line-height: 1.55;
    }
    .pk-stage-index {
        color: var(--pk-muted);
        font-size: 0.74rem;
        font-weight: 600;
        margin-bottom: 0.3rem;
    }
    .pk-panel,
    .pk-summary-card {
        background: var(--pk-surface);
        border: 1px solid rgba(215, 222, 232, 0.92);
        border-radius: var(--pk-radius);
        box-shadow: 0 10px 32px rgba(15, 23, 42, 0.05);
        backdrop-filter: blur(16px);
        padding: 1rem 1.05rem;
    }
    .pk-summary-card + .pk-summary-card,
    .pk-panel + .pk-panel {
        margin-top: 0.8rem;
    }
    .pk-summary-card h3,
    .pk-panel h3 {
        margin: 0;
        color: var(--pk-ink);
        font-size: 1rem;
        font-weight: 650;
        letter-spacing: -0.01em;
    }
    .pk-summary-card p,
    .pk-panel p {
        margin: 0.35rem 0 0;
        color: var(--pk-subtle);
        font-size: 0.84rem;
        line-height: 1.55;
    }
    .pk-meta-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.65rem;
        margin-top: 0.75rem;
    }
    .pk-meta-item {
        padding: 0.7rem 0.78rem;
        border-radius: 14px;
        background: rgba(248, 250, 252, 0.92);
        border: 1px solid rgba(226, 232, 240, 0.9);
    }
    .pk-meta-item span {
        display: block;
        color: var(--pk-muted);
        font-size: 0.74rem;
        margin-bottom: 0.18rem;
    }
    .pk-meta-item strong {
        color: var(--pk-ink);
        font-size: 0.96rem;
        font-weight: 650;
    }
    .pk-list {
        margin: 0.72rem 0 0;
        padding: 0;
        list-style: none;
    }
    .pk-list li {
        color: var(--pk-subtle);
        font-size: 0.84rem;
        line-height: 1.55;
        padding: 0.36rem 0;
        border-top: 1px solid rgba(226, 232, 240, 0.72);
    }
    .pk-list li:first-child {
        border-top: none;
        padding-top: 0;
    }
    .pk-toolbar-note {
        color: var(--pk-subtle);
        font-size: 0.85rem;
        margin: -0.12rem 0 0.7rem;
    }
    .pk-empty-state {
        border: 1px dashed rgba(180, 191, 208, 0.9);
        border-radius: var(--pk-radius);
        padding: 1rem 1.05rem;
        background: rgba(248, 250, 252, 0.82);
        color: #475467;
    }
    .pk-inline-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin-top: 0.7rem;
    }
    .pk-inline-badge {
        border-radius: 999px;
        padding: 0.25rem 0.62rem;
        font-size: 0.74rem;
        background: rgba(248, 250, 252, 0.94);
        border: 1px solid rgba(215, 222, 232, 0.92);
        color: var(--pk-subtle);
    }
    .pk-inline-badge.good {
        background: var(--pk-good-soft);
        color: var(--pk-good);
        border-color: rgba(6, 118, 71, 0.18);
    }
    .pk-inline-badge.warn {
        background: var(--pk-warn-soft);
        color: var(--pk-warn);
        border-color: rgba(181, 71, 8, 0.18);
    }
    .pk-section-heading {
        margin: 1rem 0 0.8rem;
    }
    .pk-section-heading h2 {
        margin: 0;
        color: var(--pk-ink);
        font-size: 1.35rem;
        line-height: 1.35;
        letter-spacing: -0.02em;
    }
    .pk-section-heading p {
        margin: 0.25rem 0 0;
        color: var(--pk-subtle);
        font-size: 0.92rem;
    }
    .kb-catalog {
        margin: 0.9rem 0 1rem;
    }
    .kb-catalog-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 0.7rem;
    }
    .kb-catalog-card {
        background: rgba(255, 255, 255, 0.82);
        border: 1px solid rgba(215, 222, 232, 0.88);
        border-radius: 20px;
        padding: 0.95rem 1rem;
        min-height: 182px;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
    }
    .kb-catalog-card.active {
        border-color: rgba(47, 111, 237, 0.28);
        box-shadow: 0 12px 32px rgba(47, 111, 237, 0.1);
        background: linear-gradient(135deg, rgba(238, 244, 255, 0.95), rgba(255, 255, 255, 0.96));
    }
    .kb-card-top {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 0.5rem;
        margin-bottom: 0.48rem;
    }
    .kb-card-title {
        font-size: 1rem;
        font-weight: 700;
        color: var(--pk-ink);
        line-height: 1.3;
        letter-spacing: -0.01em;
    }
    .kb-card-status {
        white-space: nowrap;
        border-radius: 999px;
        padding: 0.16rem 0.54rem;
        font-size: 0.73rem;
        border: 1px solid rgba(215, 222, 232, 0.92);
        color: var(--pk-subtle);
        background: rgba(248, 250, 252, 0.9);
    }
    .kb-card-status.active {
        color: var(--pk-accent);
        border-color: rgba(47, 111, 237, 0.2);
        background: rgba(238, 244, 255, 0.95);
    }
    .kb-card-stage {
        font-size: 0.78rem;
        color: var(--pk-subtle);
        margin-bottom: 0.45rem;
    }
    .kb-card-summary {
        font-size: 0.84rem;
        color: #475467;
        line-height: 1.58;
        margin-bottom: 0.55rem;
    }
    .kb-card-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
        margin-top: auto;
    }
    .kb-card-tag {
        font-size: 0.73rem;
        line-height: 1;
        color: var(--pk-subtle);
        background: rgba(248, 250, 252, 0.92);
        border: 1px solid rgba(226, 232, 240, 0.88);
        border-radius: 999px;
        padding: 0.28rem 0.52rem;
    }
    div[data-testid="stMetric"] {
        border: 1px solid rgba(215, 222, 232, 0.9);
        border-radius: 18px;
        padding: 0.7rem 0.8rem;
        background: rgba(255, 255, 255, 0.84);
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
    }
    div[data-testid="stMetricLabel"] {
        color: var(--pk-subtle);
    }
    div[data-testid="stMetricValue"] {
        color: var(--pk-ink);
    }
    div[data-testid="stForm"],
    div[data-testid="stExpander"] {
        border-radius: 18px;
        border: 1px solid rgba(215, 222, 232, 0.9);
        background: rgba(255, 255, 255, 0.84);
        box-shadow: 0 10px 32px rgba(15, 23, 42, 0.04);
    }
    div[data-testid="stExpander"] details > summary {
        min-height: 3rem;
    }
    div[data-testid="stTabs"] button {
        font-weight: 600;
    }
    div[data-testid="stButton"] > button {
        min-height: 2.6rem;
        border-radius: 14px;
        white-space: normal;
        border: 1px solid rgba(215, 222, 232, 0.95);
    }
    div[data-testid="stButton"] > button[kind="primary"] {
        border-color: rgba(47, 111, 237, 0.2);
        box-shadow: 0 8px 24px rgba(47, 111, 237, 0.16);
    }
    textarea,
    input {
        font-size: 0.95rem !important;
    }
    div[data-testid="stHeaderActionElements"],
    div[data-testid="stToolbar"],
    a[href^="#"] {
        display: none !important;
    }
    @media (max-width: 900px) {
        .pk-stage-strip,
        .pk-meta-grid,
        .kb-catalog-grid {
            grid-template-columns: 1fr;
        }
        .block-container {
            padding-left: 0.9rem;
            padding-right: 0.9rem;
        }
    }
    @media (max-width: 640px) {
        .main-title {
            padding: 1rem;
            border-radius: 20px;
        }
        .main-title h1 {
            font-size: 1.28rem;
        }
        .main-title p {
            font-size: 0.87rem;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.22rem !important;
        }
    }
</style>
""",
        unsafe_allow_html=True,
    )


def render_professional_knowledge_system(
    user_id: int | None = None,
    username: str | None = None,
    *,
    standalone: bool = False,
) -> None:
    """Render the portable professional knowledge recognition system.

    Host apps can pass their authenticated ``user_id`` and ``username``.
    Standalone mode falls back to ``user_id=1`` inside ``knowledge_base``.
    """

    if user_id is not None:
        st.session_state["user_id"] = user_id
    if username is not None:
        st.session_state["username"] = username

    ensure_db()
    inject_professional_knowledge_styles()

    render_knowledge_page()
