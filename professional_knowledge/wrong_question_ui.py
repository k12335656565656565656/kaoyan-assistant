from __future__ import annotations

import streamlit as st

from repositories.wrong_question_repo import (
    bulk_create_wrong_questions,
    count_user_wrong_questions,
    delete_wrong_question,
    list_user_wrong_questions,
    touch_wrong_question_review,
    update_wrong_question_status,
)
from services.wrong_question_import_service import import_wrong_question_files


_WRONG_DRAFT_FIELDS = [
    "question",
    "user_answer",
    "correct_answer",
    "explanation",
    "subject",
    "chapter_name",
    "tags",
]


def _ensure_wrong_question_draft_state() -> None:
    if "wrong_question_drafts" not in st.session_state:
        st.session_state["wrong_question_drafts"] = []
    if "wrong_question_import_warnings" not in st.session_state:
        st.session_state["wrong_question_import_warnings"] = []


def _wrong_draft_widget_key(draft_id: str, field_name: str) -> str:
    return f"wrong_draft_{draft_id}_{field_name}"


def _tags_to_text(value) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    return str(value)


def _text_to_tags(value: str) -> list[str]:
    return [item.strip() for item in (value or "").replace("，", ",").replace("；", ",").replace("、", ",").split(",") if item.strip()]


def _sync_wrong_question_draft(draft_id: str, fallback: dict) -> dict:
    updated = dict(fallback)
    for field_name in _WRONG_DRAFT_FIELDS:
        widget_key = _wrong_draft_widget_key(draft_id, field_name)
        if field_name == "tags":
            updated[field_name] = _text_to_tags(st.session_state.get(widget_key, _tags_to_text(fallback.get(field_name))))
        else:
            updated[field_name] = st.session_state.get(widget_key, fallback.get(field_name, ""))
    updated["_draft_id"] = draft_id
    return updated


def _replace_wrong_question_draft(updated_draft: dict) -> None:
    updated_drafts = []
    for draft in st.session_state.get("wrong_question_drafts", []):
        if draft.get("_draft_id") == updated_draft.get("_draft_id"):
            updated_drafts.append(updated_draft)
        else:
            updated_drafts.append(draft)
    st.session_state["wrong_question_drafts"] = updated_drafts


def _remove_wrong_question_draft(draft_id: str) -> None:
    st.session_state["wrong_question_drafts"] = [
        draft for draft in st.session_state.get("wrong_question_drafts", [])
        if draft.get("_draft_id") != draft_id
    ]


def _clear_wrong_question_drafts() -> None:
    for draft in st.session_state.get("wrong_question_drafts", []):
        draft_id = draft.get("_draft_id")
        for field_name in _WRONG_DRAFT_FIELDS:
            widget_key = _wrong_draft_widget_key(draft_id, field_name)
            if widget_key in st.session_state:
                del st.session_state[widget_key]
    st.session_state["wrong_question_drafts"] = []
    st.session_state["wrong_question_import_warnings"] = []


def _render_wrong_question_import_panel(
    user_id: int,
    subjects: list[str],
    *,
    image_ocr_fn,
    pdf_ocr_fn,
    pdf_ocr_available: bool,
) -> None:
    st.subheader("批量上传错题")
    st.caption("适合把错题截图成批上传。系统会先 OCR，再生成可编辑草稿，最后统一加入错题本。")

    with st.form("wrong_question_batch_import"):
        subject = st.selectbox("学科", subjects, key="wrong_question_subject")
        chapter_name = st.text_input("章节 / 批次名称", placeholder="例如：英语阅读错题第1批")
        tags_text = st.text_input("标签（逗号分隔）", placeholder="例如：阅读, 词汇, 真题")
        uploaded_files = st.file_uploader(
            "上传错题截图或文档",
            type=["png", "jpg", "jpeg", "pdf", "txt"],
            accept_multiple_files=True,
            key="wrong_question_files",
        )
        submitted = st.form_submit_button("批量识别错题", use_container_width=True, type="primary")

    if submitted:
        if not uploaded_files:
            st.warning("请至少上传一个错题文件。")
        else:
            with st.spinner(f"正在识别 {len(uploaded_files)} 个文件..."):
                drafts, warnings = import_wrong_question_files(
                    uploaded_files,
                    subject=subject,
                    chapter_name=chapter_name,
                    tags=tags_text,
                    image_ocr_fn=image_ocr_fn,
                    pdf_ocr_fn=pdf_ocr_fn,
                    pdf_ocr_available=pdf_ocr_available,
                )
            st.session_state["wrong_question_drafts"] = drafts
            st.session_state["wrong_question_import_warnings"] = warnings
            st.rerun()

    draft_warnings = st.session_state.get("wrong_question_import_warnings") or []
    for warning in draft_warnings:
        st.warning(warning)

    drafts = st.session_state.get("wrong_question_drafts") or []
    if not drafts:
        st.info("当前没有待确认的错题草稿。上传截图后，会先在这里做 OCR 草稿确认。")
        return

    metric1, metric2 = st.columns(2)
    metric1.metric("待确认错题", len(drafts))
    metric2.metric("当前错题总量", count_user_wrong_questions(user_id))

    toolbar_left, toolbar_right = st.columns(2)
    with toolbar_left:
        if st.button("全部加入错题本", use_container_width=True, key="save_all_wrong_question_drafts"):
            payload = []
            for draft in drafts:
                draft_id = draft.get("_draft_id")
                payload.append(_sync_wrong_question_draft(draft_id, draft))
            saved_count = bulk_create_wrong_questions(user_id, payload)
            _clear_wrong_question_drafts()
            st.success(f"已加入 {saved_count} 条错题。")
            st.rerun()
    with toolbar_right:
        if st.button("清空当前草稿", use_container_width=True, key="clear_all_wrong_question_drafts"):
            _clear_wrong_question_drafts()
            st.rerun()

    for idx, draft in enumerate(drafts, start=1):
        draft_id = draft.get("_draft_id")
        title = draft.get("source_filename") or f"错题草稿 {idx}"
        with st.expander(f"{idx}. {title}", expanded=False):
            if draft.get("warnings"):
                for warning in draft.get("warnings", []):
                    st.warning(warning)

            st.text_area("题目内容", value=draft.get("question", ""), height=180, key=_wrong_draft_widget_key(draft_id, "question"))
            c1, c2 = st.columns(2)
            with c1:
                st.text_input("学科", value=draft.get("subject", ""), key=_wrong_draft_widget_key(draft_id, "subject"))
                st.text_area("你的答案", value=draft.get("user_answer", ""), height=80, key=_wrong_draft_widget_key(draft_id, "user_answer"))
                st.text_input("标签", value=_tags_to_text(draft.get("tags")), key=_wrong_draft_widget_key(draft_id, "tags"))
            with c2:
                st.text_input("章节 / 批次", value=draft.get("chapter_name", ""), key=_wrong_draft_widget_key(draft_id, "chapter_name"))
                st.text_input("正确答案", value=draft.get("correct_answer", ""), key=_wrong_draft_widget_key(draft_id, "correct_answer"))
                st.text_area("解析", value=draft.get("explanation", ""), height=80, key=_wrong_draft_widget_key(draft_id, "explanation"))

            st.caption(f"来源文件：{draft.get('source_filename') or '未知'} · 类型：{draft.get('source_file_type') or '未知'}")
            if draft.get("source_text"):
                st.text_area(
                    "OCR 原文",
                    value=draft.get("source_text", ""),
                    height=120,
                    key=f"wrong_source_text_{draft_id}",
                    disabled=True,
                )

            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("保存修改", key=f"save_wrong_draft_{draft_id}", use_container_width=True):
                    _replace_wrong_question_draft(_sync_wrong_question_draft(draft_id, draft))
                    st.rerun()
            with b2:
                if st.button("删除草稿", key=f"delete_wrong_draft_{draft_id}", use_container_width=True):
                    _remove_wrong_question_draft(draft_id)
                    st.rerun()
            with b3:
                if st.button("加入错题本", key=f"persist_wrong_draft_{draft_id}", use_container_width=True, type="primary"):
                    payload = _sync_wrong_question_draft(draft_id, draft)
                    bulk_create_wrong_questions(user_id, [payload])
                    _remove_wrong_question_draft(draft_id)
                    st.success("已加入错题本。")
                    st.rerun()


def _render_wrong_question_library(user_id: int, subjects: list[str]) -> None:
    st.subheader("错题本")
    filter_col, status_col, search_col = st.columns([1, 1, 1.6])
    with filter_col:
        selected_subject = st.selectbox("学科筛选", ["全部"] + subjects, key="wrong_repo_subject")
    with status_col:
        selected_status = st.selectbox("状态筛选", ["全部", "active", "mastered"], key="wrong_repo_status")
    with search_col:
        search_query = st.text_input("搜索错题", placeholder="按题目、章节、答案或来源文件搜索", key="wrong_repo_search")

    items = list_user_wrong_questions(
        user_id,
        subject=selected_subject,
        status=selected_status,
        search=search_query,
        limit=300,
    )
    if not items:
        st.info("当前没有匹配的错题记录。")
        return

    active_count = sum(1 for item in items if item.get("status") == "active")
    mastered_count = sum(1 for item in items if item.get("status") == "mastered")
    m1, m2, m3 = st.columns(3)
    m1.metric("当前显示", len(items))
    m2.metric("待复习", active_count)
    m3.metric("已掌握", mastered_count)

    for idx, item in enumerate(items, start=1):
        status = item.get("status") or "active"
        status_label = "待复习" if status == "active" else "已掌握"
        chapter_name = item.get("chapter_name") or "未分组"
        title = (item.get("question") or "未命名错题").replace("\n", " ")
        preview = title[:40] + ("..." if len(title) > 40 else "")
        with st.expander(f"{idx}. {preview} · {status_label} · {chapter_name}", expanded=False):
            st.markdown(f"**题目**：{item.get('question') or '暂无题目'}")
            if item.get("user_answer"):
                st.markdown(f"**你的答案**：{item.get('user_answer')}")
            if item.get("correct_answer"):
                st.markdown(f"**正确答案**：{item.get('correct_answer')}")
            if item.get("explanation"):
                st.markdown(f"**解析**：{item.get('explanation')}")
            st.caption(
                f"来源：{item.get('source_filename') or '未知文件'} · 标签：{', '.join(item.get('tags') or []) or '无'}"
            )

            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("标记已掌握", key=f"master_wrong_{item['id']}", use_container_width=True):
                    update_wrong_question_status(item["id"], "mastered")
                    st.rerun()
            with c2:
                if st.button("重新学习", key=f"relearn_wrong_{item['id']}", use_container_width=True):
                    touch_wrong_question_review(item["id"])
                    st.rerun()
            with c3:
                if st.button("删除错题", key=f"delete_wrong_{item['id']}", use_container_width=True):
                    delete_wrong_question(item["id"])
                    st.rerun()


def render_wrong_question_workspace(
    user_id: int,
    subjects: list[str],
    *,
    image_ocr_fn,
    pdf_ocr_fn,
    pdf_ocr_available: bool,
) -> None:
    _ensure_wrong_question_draft_state()
    upload_tab, library_tab = st.tabs(["批量上传", "错题管理"])
    with upload_tab:
        _render_wrong_question_import_panel(
            user_id,
            subjects,
            image_ocr_fn=image_ocr_fn,
            pdf_ocr_fn=pdf_ocr_fn,
            pdf_ocr_available=pdf_ocr_available,
        )
    with library_tab:
        _render_wrong_question_library(user_id, subjects)
