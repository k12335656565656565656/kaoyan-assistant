"""
专业知识库模块 — 独立包
功能：上传资料 · OCR识别 · 错题本 · 复习本 · AI出题
"""

import streamlit as st
import sqlite3
import os
import hashlib
import html
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
import json
import base64
import urllib.request
from pathlib import Path
from uuid import uuid4

from professional_knowledge.catalog import (
    get_rag_knowledge_base_by_subject,
    list_enabled_subjects,
    list_rag_knowledge_bases,
    save_custom_subject_profile,
)
from professional_knowledge.wrong_question_ui import render_wrong_question_workspace
from repositories.knowledge_repo import (
    ensure_knowledge_schema,
    list_user_knowledge_points,
    save_confirmed_knowledge_points,
    update_knowledge_review_content,
)
from repositories.material_repo import (
    create_material,
    ensure_material_schema,
    list_resumable_materials,
    mark_material_status,
    save_confirmed_text,
    save_extraction_result,
    save_workflow_snapshot,
)
from repositories.wrong_question_repo import count_user_wrong_questions
from schemas.knowledge_schema import (
    knowledge_point_to_dict,
    normalize_knowledge_point_draft,
    validate_required_fields,
)
from schemas.material_schema import MaterialResult
from services.adaptive_ocr_service import (
    extract_pdf_text_adaptively,
    extract_text_adaptively,
    is_rapid_ocr_available,
)
from services.llm_gateway import simple_prompt_completion
from services.knowledge_json_extractor import extract_knowledge_points_as_drafts
from services.local_material_source_service import (
    get_local_material_root,
    get_local_material_source_for_subject,
    get_local_material_source_hint,
    list_local_material_files,
    read_local_material,
)
from services.material_router import route_material_input
from services.paddle_ocr_service import is_paddle_ocr_available
from services.professional_knowledge_task_service import (
    create_task as create_professional_task,
    list_recent_tasks,
    update_task_status as update_professional_task_status,
)

# ==================== 配置（从环境变量读取） ====================
MEMORY_DB = os.environ.get("MEMORY_DB", "data/memory.db")
API_KEY = os.environ.get("AI_API_KEY", "")
API_BASE = os.environ.get("AI_API_BASE", "https://api.xiaomimimo.com/v1")
UMI_OCR_URL = os.environ.get("UMI_OCR_URL", "http://localhost:1224")


def _escape_html(value):
    return html.escape(str(value if value is not None else ""), quote=True)


# ==================== 数据库初始化 ====================

def init_knowledge_db(conn):
    """创建专业知识库相关的 4 张表"""
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS user_materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject TEXT,
        filename TEXT,
        chapter_name TEXT,
        file_path TEXT,
        file_type TEXT,
        processing_status TEXT DEFAULT 'pending',
        knowledge_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS user_knowledge (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        material_id INTEGER,
        subject TEXT,
        chapter_name TEXT,
        knowledge_name TEXT,
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS user_wrong_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        knowledge_id INTEGER,
        subject TEXT,
        chapter_name TEXT,
        question TEXT,
        user_answer TEXT,
        correct_answer TEXT,
        explanation TEXT,
        error_count INTEGER DEFAULT 1,
        status TEXT DEFAULT 'active',
        last_reviewed TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS user_review_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        knowledge_id INTEGER,
        review_date TEXT,
        mastered INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    ensure_material_schema(conn)
    ensure_knowledge_schema(conn)


def ensure_db():
    """自动创建数据库和表（独立运行时调用）"""
    os.makedirs(os.path.dirname(MEMORY_DB) or "data", exist_ok=True)
    conn = sqlite3.connect(MEMORY_DB)
    init_knowledge_db(conn)
    conn.commit()
    conn.close()


# ==================== LLM 辅助 ====================

def _call_llm_api(prompt, model="mimo-v2.5", max_tokens=1500):
    return simple_prompt_completion(
        prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=0.3,
        timeout=90,
    )


# ==================== PDF / 图片 / OCR ====================

def extract_text_from_pdf(file_path):
    """用 PyMuPDF 提取 PDF 文本"""
    try:
        import fitz
        doc = fitz.open(str(file_path))
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text[:5000]
    except:
        return ""


def check_umiocr_available():
    """检查 umi-ocr API 是否可用"""
    try:
        import requests
        resp = requests.get(f"{UMI_OCR_URL}/api/status", timeout=5)
        return resp.status_code == 200
    except:
        return False


def extract_text_from_pdf_umiocr(file_path):
    """用 umi-ocr API 逐页识别 PDF（中文 OCR）"""
    import fitz
    doc = fitz.open(str(file_path))
    all_text = []
    total_pages = min(len(doc), 20)

    for page_num in range(total_pages):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        img_b64 = base64.b64encode(img_bytes).decode()

        try:
            import requests
            resp = requests.post(
                f"{UMI_OCR_URL}/api/ocr",
                json={"base64": img_b64},
                timeout=30
            )
            result = resp.json()
            if result.get("text"):
                all_text.append(f"=== 第{page_num+1}页 ===\n{result['text']}")
        except Exception as e:
            print(f"第{page_num+1}页 OCR 失败: {e}")

    doc.close()
    return "\n\n".join(all_text)


def extract_text_from_pdf_paddleocr(file_path, progress_callback=None):
    """兼容旧入口，内部使用自适应 OCR 管线。"""
    return extract_pdf_text_adaptively(
        file_path,
        progress_callback=progress_callback,
    )


def extract_text_from_image(file_bytes):
    """用自适应本地 OCR 识别图片中的文字，不走 AI 多模态。"""
    if not (is_rapid_ocr_available() or is_paddle_ocr_available()):
        raise RuntimeError("OCR 服务不可用。文字型 PDF 仍可直接提取；扫描型 PDF 或图片可能无法识别。")
    result = extract_text_adaptively(
        file_bytes,
        lang=os.environ.get("PADDLE_OCR_LANG", "ch"),
    )
    return result.text


def extract_knowledge_from_pdf_images(file_path, subject, chapter_name):
    """将 PDF 每页转为图片 OCR 后，再从文本中提取知识点。"""
    import fitz
    doc = fitz.open(str(file_path))
    page_texts = []

    for page_num in range(min(len(doc), 20)):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=150)
        try:
            page_text = extract_text_from_image(pix.tobytes("png"))
            if page_text:
                page_texts.append(f"=== 第{page_num + 1}页 ===\n{page_text}")
        except Exception:
            pass

    doc.close()
    return extract_knowledge_from_text("\n\n".join(page_texts), subject, chapter_name) if page_texts else ""


def extract_knowledge_from_image(file_bytes, subject, chapter_name):
    """图片先走 PaddleOCR，再从 OCR 文本中提取知识点。"""
    image_text = extract_text_from_image(file_bytes)
    return extract_knowledge_from_text(image_text, subject, chapter_name) if image_text else ""


def extract_knowledge_from_text(content, subject, chapter_name):
    """用 LLM 从文本中提取知识点"""
    prompt = f"""请从以下内容中提取知识点，输出格式为：
知识点1: [知识点名称]
知识点2: [知识点名称]
...
每个知识点简要说明其核心概念（1-2句话）。

学科：{subject}
章节：{chapter_name}

内容：
{content[:3000]}"""
    return _call_llm_api(prompt, model="mimo-v2.5", max_tokens=1500)


def generate_review_expansion(point):
    """为单个知识点生成解释、考法、追问和复习卡片。"""
    prompt = f"""你是考研计算机专业课复习教练。请基于下面这个已确认知识点生成复习内容。

要求：
1. 不编造原文没有支持的具体事实。
2. 如果需要延伸，必须标注“延伸理解”。
3. 输出 Markdown，包含：核心解释、常见考法、易错提醒、复习卡片、追问。
4. 复习卡片使用 Q/A 格式，控制在 3 张以内。

知识点：
{json.dumps(point, ensure_ascii=False, indent=2)}
"""
    return _call_llm_api(prompt, model="mimo-v2.5", max_tokens=1600)


# ==================== 数据库操作 ====================

def save_knowledge_points(user_id, material_id, subject, chapter_name, llm_result):
    """保存 LLM 提取的知识点到数据库"""
    conn = sqlite3.connect(MEMORY_DB)
    c = conn.cursor()
    lines_kb = [l.strip() for l in llm_result.split("\n") if l.strip().startswith("知识点")]
    count = 0
    for line_kb in lines_kb:
        name_kb = line_kb.split(":", 1)[-1].strip() if ":" in line_kb else line_kb.strip()
        c.execute("""INSERT INTO user_knowledge
            (user_id, material_id, subject, chapter_name, knowledge_name, content)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, material_id, subject, chapter_name, name_kb, llm_result))
        count += 1
    c.execute("UPDATE user_materials SET processing_status='done', knowledge_count=? WHERE id=?",
             (count, material_id))
    conn.commit()
    conn.close()
    return count


def get_user_materials(user_id, subject):
    """获取用户上传的资料列表"""
    conn = sqlite3.connect(MEMORY_DB)
    c = conn.cursor()
    c.execute("SELECT id, filename, chapter_name, processing_status, knowledge_count FROM user_materials WHERE user_id=? AND subject=? ORDER BY created_at DESC",
             (user_id, subject))
    rows = c.fetchall()
    conn.close()
    return rows


def get_user_knowledge(user_id, subject):
    """获取用户知识点列表"""
    conn = sqlite3.connect(MEMORY_DB)
    c = conn.cursor()
    c.execute("SELECT chapter_name, knowledge_name, content FROM user_knowledge WHERE user_id=? AND subject=? ORDER BY chapter_name, id",
             (user_id, subject))
    rows = c.fetchall()
    conn.close()
    return rows


def get_user_wrong_questions(user_id, subject):
    """获取用户错题列表"""
    conn = sqlite3.connect(MEMORY_DB)
    c = conn.cursor()
    c.execute("""SELECT id, chapter_name, question, user_answer, correct_answer, explanation, error_count
        FROM user_wrong_questions WHERE user_id=? AND subject=? AND status='active'
        ORDER BY error_count DESC""", (user_id, subject))
    rows = c.fetchall()
    conn.close()
    return rows


def add_wrong_question(user_id, subject, question, user_answer, correct_answer, explanation):
    """添加错题"""
    conn = sqlite3.connect(MEMORY_DB)
    c = conn.cursor()
    c.execute("""INSERT INTO user_wrong_questions
        (user_id, subject, question, user_answer, correct_answer, explanation)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, subject, question, user_answer, correct_answer, explanation))
    conn.commit()
    conn.close()


def mark_wrong_mastered(question_id):
    """标记错题已掌握"""
    conn = sqlite3.connect(MEMORY_DB)
    conn.execute("UPDATE user_wrong_questions SET status='mastered' WHERE id=?", (question_id,))
    conn.commit()
    conn.close()


def relearn_wrong(question_id):
    """重新学习错题"""
    conn = sqlite3.connect(MEMORY_DB)
    conn.execute("UPDATE user_wrong_questions SET last_reviewed=datetime('now') WHERE id=?", (question_id,))
    conn.commit()
    conn.close()


def get_review_items(user_id, subject):
    """获取待复习知识点（从错题中提取）"""
    conn = sqlite3.connect(MEMORY_DB)
    c = conn.cursor()
    c.execute("""SELECT DISTINCT chapter_name, question, explanation, last_reviewed
        FROM user_wrong_questions
        WHERE user_id=? AND subject=? AND status='active'
        ORDER BY last_reviewed ASC""",
        (user_id, subject))
    rows = c.fetchall()
    conn.close()
    return rows


_DRAFT_LIST_FIELDS = [
    "exam_question_styles",
    "keywords",
    "related_concepts",
    "pitfalls",
    "tags",
]

_DRAFT_EDITABLE_FIELDS = [
    "knowledge_name",
    "knowledge_type",
    "subject",
    "chapter_name",
    "core_definition",
    "exam_question_styles",
    "keywords",
    "related_concepts",
    "pitfalls",
    "example_or_application",
    "review_priority",
    "source_text",
    "source_page",
    "source_location",
    "tags",
    "mastery_state",
    "is_ai_expansion",
    "uncertainty_note",
]


def _ensure_session_draft_state():
    if "knowledge_drafts" not in st.session_state:
        legacy_points = st.session_state.get("_draft_knowledge_points") or []
        st.session_state["knowledge_drafts"] = [_prepare_draft_for_session(point) for point in legacy_points]
    if "confirmed_knowledge_drafts" not in st.session_state:
        st.session_state["confirmed_knowledge_drafts"] = []
    if "deleted_knowledge_draft_count" not in st.session_state:
        st.session_state["deleted_knowledge_draft_count"] = 0
    if "knowledge_draft_warnings" not in st.session_state:
        st.session_state["knowledge_draft_warnings"] = st.session_state.get("_draft_knowledge_warnings") or []


def _prepare_draft_for_session(point):
    normalized = knowledge_point_to_dict(normalize_knowledge_point_draft(point))
    normalized["_draft_id"] = str(point.get("_draft_id") or uuid4().hex)
    return normalized


def _set_draft_session_data(drafts, warnings):
    st.session_state["knowledge_drafts"] = [_prepare_draft_for_session(point) for point in drafts]
    st.session_state["confirmed_knowledge_drafts"] = []
    st.session_state["deleted_knowledge_draft_count"] = 0
    st.session_state["knowledge_draft_warnings"] = list(warnings or [])
    st.session_state["_draft_knowledge_points"] = st.session_state["knowledge_drafts"]
    st.session_state["_draft_knowledge_warnings"] = st.session_state["knowledge_draft_warnings"]


def _sync_legacy_draft_keys():
    st.session_state["_draft_knowledge_points"] = st.session_state.get("knowledge_drafts", [])
    st.session_state["_draft_knowledge_warnings"] = st.session_state.get("knowledge_draft_warnings", [])


def _draft_widget_key(draft_id, field_name):
    return f"draft_{draft_id}_{field_name}"


def _list_field_to_text(value):
    if not value:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    return str(value)


def _build_draft_from_widget(draft_id, fallback_point):
    payload = {}
    for field_name in _DRAFT_EDITABLE_FIELDS:
        widget_key = _draft_widget_key(draft_id, field_name)
        if field_name == "is_ai_expansion":
            payload[field_name] = st.session_state.get(widget_key, fallback_point.get(field_name, False))
        elif field_name in _DRAFT_LIST_FIELDS:
            payload[field_name] = st.session_state.get(widget_key, _list_field_to_text(fallback_point.get(field_name)))
        else:
            payload[field_name] = st.session_state.get(widget_key, fallback_point.get(field_name, ""))

    normalized = knowledge_point_to_dict(normalize_knowledge_point_draft(payload))
    normalized["_draft_id"] = draft_id
    return normalized


def _replace_draft_in_session(updated_point):
    draft_id = updated_point.get("_draft_id")
    updated_drafts = []
    for point in st.session_state.get("knowledge_drafts", []):
        if point.get("_draft_id") == draft_id:
            updated_drafts.append(updated_point)
        else:
            updated_drafts.append(point)
    st.session_state["knowledge_drafts"] = updated_drafts
    _sync_legacy_draft_keys()


def _remove_draft_widget_state(draft_id):
    for field_name in _DRAFT_EDITABLE_FIELDS:
        widget_key = _draft_widget_key(draft_id, field_name)
        if widget_key in st.session_state:
            del st.session_state[widget_key]


def _remove_draft_from_session(draft_id, increment_deleted=True):
    remaining = [point for point in st.session_state.get("knowledge_drafts", []) if point.get("_draft_id") != draft_id]
    st.session_state["knowledge_drafts"] = remaining
    if increment_deleted:
        st.session_state["deleted_knowledge_draft_count"] = st.session_state.get("deleted_knowledge_draft_count", 0) + 1
    _remove_draft_widget_state(draft_id)
    _sync_legacy_draft_keys()


def _confirm_draft_in_session(point):
    confirmed = list(st.session_state.get("confirmed_knowledge_drafts", []))
    confirmed.append(point)
    st.session_state["confirmed_knowledge_drafts"] = confirmed
    _remove_draft_from_session(point.get("_draft_id"), increment_deleted=False)


def _confirm_all_drafts_in_session():
    drafts = list(st.session_state.get("knowledge_drafts", []))
    confirmed = list(st.session_state.get("confirmed_knowledge_drafts", []))
    synced_drafts = []
    for point in drafts:
        draft_id = point.get("_draft_id")
        if draft_id:
            synced_drafts.append(_build_draft_from_widget(draft_id, point))
        else:
            synced_drafts.append(point)
    confirmed.extend(synced_drafts)
    st.session_state["confirmed_knowledge_drafts"] = confirmed
    for point in drafts:
        _remove_draft_widget_state(point.get("_draft_id"))
    st.session_state["knowledge_drafts"] = []
    _sync_legacy_draft_keys()


def _clear_current_draft_session():
    for point in st.session_state.get("knowledge_drafts", []):
        _remove_draft_widget_state(point.get("_draft_id"))
    st.session_state["knowledge_drafts"] = []
    st.session_state["confirmed_knowledge_drafts"] = []
    st.session_state["deleted_knowledge_draft_count"] = 0
    st.session_state["knowledge_draft_warnings"] = []
    st.session_state["persisted_knowledge_count"] = 0
    st.session_state["last_persisted_knowledge_names"] = []
    st.session_state["persisted_confirmed_knowledge_ids"] = []
    st.session_state["_draft_knowledge_points"] = []
    st.session_state["_draft_knowledge_warnings"] = []
    st.session_state.pop("selected_draft_id", None)


def _remove_confirmed_draft_widget_state(draft_id):
    if not draft_id:
        return
    for field_name in _DRAFT_EDITABLE_FIELDS:
        widget_key = _draft_widget_key(draft_id, field_name)
        if widget_key in st.session_state:
            del st.session_state[widget_key]


def _remove_confirmed_draft_from_session(draft_id):
    confirmed = [
        point
        for point in st.session_state.get("confirmed_knowledge_drafts", [])
        if point.get("_draft_id") != draft_id
    ]
    st.session_state["confirmed_knowledge_drafts"] = confirmed
    persisted_ids = [
        item for item in st.session_state.get("persisted_confirmed_knowledge_ids", [])
        if item != draft_id
    ]
    st.session_state["persisted_confirmed_knowledge_ids"] = persisted_ids
    _remove_confirmed_draft_widget_state(draft_id)


def _restore_confirmed_draft_to_queue(draft_id):
    confirmed = list(st.session_state.get("confirmed_knowledge_drafts", []))
    restored_point = None
    remaining_confirmed = []
    for point in confirmed:
        if point.get("_draft_id") == draft_id and restored_point is None:
            restored_point = point
        else:
            remaining_confirmed.append(point)

    if restored_point is None:
        return False

    drafts = list(st.session_state.get("knowledge_drafts", []))
    drafts.insert(0, restored_point)
    st.session_state["knowledge_drafts"] = drafts
    st.session_state["confirmed_knowledge_drafts"] = remaining_confirmed
    st.session_state["selected_draft_id"] = draft_id
    persisted_ids = [
        item for item in st.session_state.get("persisted_confirmed_knowledge_ids", [])
        if item != draft_id
    ]
    st.session_state["persisted_confirmed_knowledge_ids"] = persisted_ids
    _sync_legacy_draft_keys()
    return True


def _ensure_persist_state():
    if "persisted_knowledge_count" not in st.session_state:
        st.session_state["persisted_knowledge_count"] = 0
    if "last_persisted_knowledge_names" not in st.session_state:
        st.session_state["last_persisted_knowledge_names"] = []
    if "persisted_confirmed_knowledge_ids" not in st.session_state:
        st.session_state["persisted_confirmed_knowledge_ids"] = []


def _build_active_workflow_snapshot():
    return {
        "remaining_drafts": list(st.session_state.get("knowledge_drafts") or []),
        "confirmed_drafts": list(st.session_state.get("confirmed_knowledge_drafts") or []),
        "deleted_count": int(st.session_state.get("deleted_knowledge_draft_count", 0) or 0),
        "warnings": list(st.session_state.get("knowledge_draft_warnings") or []),
        "persisted_draft_ids": list(st.session_state.get("persisted_confirmed_knowledge_ids") or []),
    }


def _persist_active_workflow_snapshot(status="drafted"):
    material_id = st.session_state.get("_ocr_material_id")
    if not material_id:
        return False
    conn = sqlite3.connect(MEMORY_DB)
    try:
        snapshot = _build_active_workflow_snapshot()
        if status == "drafted":
            confirmed_ids = {
                point.get("_draft_id")
                for point in snapshot.get("confirmed_drafts") or []
                if point.get("_draft_id")
            }
            persisted_ids = set(snapshot.get("persisted_draft_ids") or [])
            if (
                not snapshot.get("remaining_drafts")
                and confirmed_ids
                and confirmed_ids.issubset(persisted_ids)
            ):
                status = "done"
        save_workflow_snapshot(
            conn,
            material_id,
            snapshot,
            status=status,
        )
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        st.warning(f"当前操作已在页面中生效，但自动保存恢复进度失败：{exc}")
        return False
    finally:
        conn.close()


def _persist_active_confirmed_text(text, status="text_confirmed"):
    material_id = st.session_state.get("_ocr_material_id")
    if not material_id:
        return False
    conn = sqlite3.connect(MEMORY_DB)
    try:
        save_confirmed_text(conn, material_id, text, status=status)
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        st.error(f"保存人工确认文本失败：{exc}")
        return False
    finally:
        conn.close()


def _apply_workflow_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        return
    remaining = snapshot.get("remaining_drafts") or []
    confirmed = snapshot.get("confirmed_drafts") or []
    st.session_state["knowledge_drafts"] = [_prepare_draft_for_session(point) for point in remaining]
    st.session_state["confirmed_knowledge_drafts"] = [_prepare_draft_for_session(point) for point in confirmed]
    st.session_state["deleted_knowledge_draft_count"] = int(snapshot.get("deleted_count", 0) or 0)
    st.session_state["knowledge_draft_warnings"] = list(snapshot.get("warnings") or [])
    st.session_state["persisted_confirmed_knowledge_ids"] = list(snapshot.get("persisted_draft_ids") or [])
    _sync_legacy_draft_keys()


def _restore_material_record(record):
    payload = dict(record.get("material_result") or {})
    payload.setdefault("source_type", record.get("source_type") or "pasted_text")
    payload.setdefault("process_method", record.get("process_method") or "pasted_text")
    payload.setdefault("raw_extracted_text", record.get("raw_extracted_text") or "")
    payload.setdefault("extracted_text", record.get("extracted_text") or "")
    payload.setdefault("confidence", 0.0)
    confirmed_text = record.get("confirmed_text") or ""
    if confirmed_text:
        payload["extracted_text"] = confirmed_text
    material_result = MaterialResult.from_dict(payload)
    _set_active_material_state(
        material_id=record.get("id"),
        chapter_name=record.get("chapter_name") or "",
        subject=record.get("subject") or "其他",
        file_type=record.get("file_type") or "pasted_text",
        filename=record.get("filename") or "material.txt",
        material_result=material_result,
    )
    st.session_state.pop("_pk_task_id", None)
    _apply_workflow_snapshot(record.get("workflow_snapshot") or {})


def _material_status_label(status):
    return {
        "pending": "等待处理",
        "extracted": "文本待核对",
        "text_confirmed": "文本已核对",
        "drafted": "知识点待确认",
        "failed": "处理失败",
    }.get(status or "pending", status or "等待处理")


def _render_stage_strip(active_step):
    steps = [
        ("1", "资料导入", "导入 PDF、图片或粘贴文本，系统先做提取与清洗。"),
        ("2", "确认知识点", "逐条核对候选草稿，保留可追溯的原文依据。"),
        ("3", "私有知识库", "围绕已确认知识点检索、复习、扩展和后续 RAG。"),
    ]
    cards = []
    for index, title, desc in steps:
        active_class = " active" if active_step == index else ""
        cards.append(
            (
                f'<div class="pk-stage-card{active_class}">'
                f'<div class="pk-stage-index">STEP {index}</div>'
                f"<h3>{title}</h3>"
                f"<p>{desc}</p>"
                f"</div>"
            )
        )
    st.markdown(f'<div class="pk-stage-strip">{"".join(cards)}</div>', unsafe_allow_html=True)


def _render_info_card(title, body, metrics=None, badges=None, kicker=""):
    metric_html = ""
    if metrics:
        items = []
        for label, value in metrics:
            items.append(
                (
                    '<div class="pk-meta-item">'
                    f"<span>{_escape_html(label)}</span>"
                    f"<strong>{_escape_html(value)}</strong>"
                    "</div>"
                )
            )
        metric_html = f'<div class="pk-meta-grid">{"".join(items)}</div>'

    badge_html = ""
    if badges:
        badge_nodes = []
        for text, tone in badges:
            tone_class = f" {tone}" if tone else ""
            badge_nodes.append(
                f'<span class="pk-inline-badge{tone_class}">{_escape_html(text)}</span>'
            )
        badge_html = f'<div class="pk-inline-badges">{"".join(badge_nodes)}</div>'

    kicker_html = f'<div class="pk-kicker">{_escape_html(kicker)}</div>' if kicker else ""
    st.markdown(
        (
            '<div class="pk-summary-card">'
            f"{kicker_html}"
            f"<h3>{_escape_html(title)}</h3>"
            f"<p>{_escape_html(body)}</p>"
            f"{metric_html}"
            f"{badge_html}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_material_report(material_result):
    report = material_result.get("clean_report") or {}
    pdf_diagnostics = material_result.get("pdf_diagnostics") or {}
    ocr_report = material_result.get("ocr_report") or {}
    warnings = _filter_material_warnings(material_result.get("warnings") or [])
    badges = []
    process_method = material_result.get("process_method") or "unknown"
    confidence = material_result.get("confidence", 0.0)
    if process_method == "pdf_text_extract":
        badges.append(("文字型 PDF 直提", "good"))
    elif process_method == "pdf_ocr":
        badges.append(("OCR 回退", "warn"))
    elif process_method == "image_ocr":
        badges.append(("图片 OCR", "warn"))
    else:
        badges.append((process_method, ""))
    badges.append((f"置信度 {confidence:.2f}", ""))

    _render_info_card(
        "资料解析摘要",
        "参考 NotebookLM 的“来源优先”逻辑，先保留资料事实，再进入知识点抽取。",
        metrics=[
            ("页码锚点", report.get("page_markers", 0)),
            ("题目片段", report.get("question_blocks", 0)),
            ("清理行数", report.get("removed_noise_lines", 0)),
            ("行内噪声", report.get("removed_inline_noise", 0)),
        ],
        badges=badges,
        kicker="资料工作台",
    )

    if pdf_diagnostics:
        _render_info_card(
            "PDF 预检",
            "参考 MinerU / Unstructured 的思路，在正式抽取前先判断是不是图片型、重复水印型或可疑文字层。",
            metrics=[
                ("整页图片页", f"{pdf_diagnostics.get('image_dominant_pages', 0)}/{pdf_diagnostics.get('page_count', 0)}"),
                ("重复文字页", f"{pdf_diagnostics.get('repeated_text_pages', 0)}/{pdf_diagnostics.get('page_count', 0)}"),
                ("水印疑似页", f"{pdf_diagnostics.get('watermark_like_pages', 0)}/{pdf_diagnostics.get('page_count', 0)}"),
                ("是否强制 OCR", "是" if pdf_diagnostics.get("needs_ocr") else "否"),
            ],
            badges=[
                ("自动预检", "good"),
                ("图片型检测" if pdf_diagnostics.get("needs_ocr") else "文字层可信", "warn" if pdf_diagnostics.get("needs_ocr") else "good"),
            ],
            kicker="防患检测",
        )

    if ocr_report:
        _render_info_card(
            "OCR 识别质量",
            "默认使用 RapidOCR 快速识别，仅在页面质量不足时增强图片或回退 PaddleOCR。",
            metrics=[
                ("主要引擎", ocr_report.get("primary_engine", "unknown")),
                ("处理页数", ocr_report.get("pages_processed", 0)),
                ("平均质量", f"{ocr_report.get('average_quality', 0.0):.2f}"),
                ("重复页眉清理", ocr_report.get("repeated_lines_removed", 0)),
            ],
            badges=[("自适应 OCR", "good")],
            kicker="识别报告",
        )

    if warnings:
        lines = "".join(f"<li>{_escape_html(warning)}</li>" for warning in warnings[:6])
        st.markdown(
            f"""
            <div class="pk-panel">
                <h3>屏蔽系统提示</h3>
                <ul class="pk-list">{lines}</ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    removed_samples = report.get("removed_line_samples") or []
    inline_samples = report.get("inline_noise_samples") or []
    preserved_samples = report.get("preserved_suspicious_samples") or []
    if removed_samples or inline_samples or preserved_samples:
        with st.expander("查看屏蔽前后对比与保留记录", expanded=False):
            if removed_samples:
                st.markdown("**已屏蔽整行噪声**")
                for sample in removed_samples:
                    st.caption(sample)
            if inline_samples:
                st.markdown("**已清理行内噪声**")
                for sample in inline_samples:
                    st.caption(sample)
            if preserved_samples:
                st.markdown("**疑似噪声但已保留**")
                st.caption("这些内容包含敏感词，但更像题干的一部分，因此没有被剪掉。")
                for sample in preserved_samples:
                    st.caption(sample)


def _filter_material_warnings(warnings):
    hidden_fragments = (
        "已清理",
        "已按页码和题号整理",
        "PDF 直接提取质量较低",
        "检测到图片主导且重复水印明显",
    )
    filtered = []
    for warning in warnings:
        if any(fragment in warning for fragment in hidden_fragments):
            continue
        if warning.startswith("PDF 检测："):
            continue
        filtered.append(warning)
    return filtered


def _show_pending_toast():
    payload = st.session_state.pop("_pending_toast", None)
    if not payload:
        return
    if isinstance(payload, str):
        st.toast(payload)
        return
    st.toast(payload.get("message", "操作完成"), icon=payload.get("icon"))


def _queue_toast(message, icon="✅"):
    st.session_state["_pending_toast"] = {"message": message, "icon": icon}


def _current_task_id():
    return st.session_state.get("_pk_task_id")


def _update_current_task(status, note=None, **updates):
    task_id = _current_task_id()
    if not task_id:
        return
    update_professional_task_status(task_id, status, note=note, **updates)


def _extract_drafts_with_progress(
    *,
    text,
    subject,
    chapter_name,
    max_points=12,
    extraction_guidance="",
):
    progress_status = st.status("正在整理待抽取文本...", expanded=True)
    progress_bar = st.progress(0)

    def update_progress(current, total, message):
        progress_value = current / max(total, 1)
        progress_bar.progress(min(progress_value, 1.0))
        progress_status.update(label=message, state="running")

    try:
        with progress_status:
            drafts, draft_warnings = extract_knowledge_points_as_drafts(
                text,
                subject=subject,
                chapter_name=chapter_name,
                max_points=max_points,
                llm_callable=lambda prompt: _call_llm_api(prompt, model="mimo-v2.5", max_tokens=4000),
                progress_callback=update_progress,
                extraction_guidance=extraction_guidance,
            )
    except Exception:
        progress_status.update(label="候选知识点抽取失败", state="error", expanded=True)
        raise

    progress_bar.progress(1.0)
    progress_status.update(
        label=f"候选知识点抽取完成，共 {len(drafts)} 条",
        state="complete",
        expanded=False,
    )
    return drafts, draft_warnings


def _render_material_library_snapshot(user_id, selected_subject):
    materials = get_user_materials(user_id, selected_subject)
    if not materials:
        st.markdown(
            """
            <div class="pk-panel">
                <h3>来源资料</h3>
                <p>当前学科还没有可复用的资料记录。导入成功后，这里会形成类似 NotebookLM 的资料书架。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    top_rows = materials[:5]
    items = []
    for material_id, filename, chapter_name, status, knowledge_count in top_rows:
        status_text = "已入库" if status == "done" else _material_status_label(status)
        items.append(
            f"<li>{_escape_html(chapter_name or filename)} · {_escape_html(filename)} · "
            f"{_escape_html(status_text)} · {_escape_html(knowledge_count)} 条知识点</li>"
        )
    st.markdown(
        f"""
        <div class="pk-panel">
            <h3>来源资料书架</h3>
            <p>按学科归档最近资料，后续可直接扩展到更多专业课和 source chunks 检索。</p>
            <ul class="pk-list">{"".join(items)}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    recent_tasks = list_recent_tasks(user_id, limit=5)
    if recent_tasks:
        task_items = []
        for task in recent_tasks:
            task_items.append(
                f"<li>{_escape_html(task.chapter_name or task.filename)} · "
                f"{_escape_html(task.status)} · {_escape_html(task.updated_at)}</li>"
            )
        st.markdown(
            f"""
            <div class="pk-panel">
                <h3>抽取任务轨迹</h3>
                <p>保留最近几次抽取流程状态，用于对比每次识别、抽取与保存结果；未完成资料请从页面顶部继续。</p>
                <ul class="pk-list">{"".join(task_items)}</ul>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_resume_material_panel(user_id):
    conn = sqlite3.connect(MEMORY_DB)
    try:
        records = list_resumable_materials(conn, user_id, limit=20)
    finally:
        conn.close()

    resumable = [
        record
        for record in records
        if record.get("confirmed_text")
        or record.get("extracted_text")
        or (record.get("workflow_snapshot") or {}).get("remaining_drafts")
        or (record.get("workflow_snapshot") or {}).get("confirmed_drafts")
    ]
    if not resumable:
        return

    _render_info_card(
        "继续上次未完成的资料",
        "文本、候选草稿和已确认队列已保存到 SQLite。刷新页面或重新启动后，可以从这里继续。",
        metrics=[
            ("可继续资料", len(resumable)),
            ("最近状态", _material_status_label(resumable[0].get("processing_status"))),
        ],
        badges=[("自动保存工作流", "good")],
        kicker="继续处理",
    )
    record_map = {str(record.get("id")): record for record in resumable if record.get("id") is not None}
    selected_id = st.selectbox(
        "选择未完成资料",
        options=list(record_map.keys()),
        format_func=lambda material_id: (
            f"{record_map[material_id].get('subject') or '未分类'} · "
            f"{record_map[material_id].get('chapter_name') or record_map[material_id].get('filename') or '未命名资料'} · "
            f"{_material_status_label(record_map[material_id].get('processing_status'))}"
        ),
        key="resume_material_id_v1",
    )
    if st.button("继续处理这份资料", use_container_width=True, type="primary", key="resume_material_v1"):
        _restore_material_record(record_map[selected_id])
        _queue_toast("已恢复资料和确认进度")
        st.rerun()


def _format_draft_option(point):
    warnings = validate_required_fields(point)
    title = point.get("knowledge_name") or "未命名知识点"
    page = point.get("source_page") or "未知页码"
    suffix = " · 待补证据" if warnings else ""
    return f"{title} · {page}{suffix}"


def _ensure_selected_draft(draft_points):
    if not draft_points:
        st.session_state.pop("selected_draft_id", None)
        return None

    draft_ids = [point.get("_draft_id") for point in draft_points]
    selected_id = st.session_state.get("selected_draft_id")
    if selected_id not in draft_ids:
        selected_id = draft_ids[0]
        st.session_state["selected_draft_id"] = selected_id
    return selected_id


def _format_repo_option(point):
    title = point.get("knowledge_name") or "未命名知识点"
    subject = point.get("subject") or "未分类"
    status = point.get("mastery_state") or "待复习"
    return f"{title} · {subject} · {status}"


# ==================== UI 渲染 ====================

def _render_knowledge_page_legacy():
    """渲染专业知识库页面（4 个 Tab）"""
    user_id = st.session_state.get("user_id", 1)
    _ensure_session_draft_state()
    _ensure_persist_state()

    if not API_KEY:
        st.warning("未设置 AI_API_KEY。系统仍可用本地规则生成候选草稿，但图片识别、AI 出题和高质量知识点抽取需要配置 API Key。")
        st.code("$env:AI_API_KEY='sk-xxx'  # Windows PowerShell", language="powershell")

    st.markdown("""
    <div class="main-title">
        <h1>📚 专业知识库</h1>
        <p>上传资料 · OCR识别 · 错题本 · 复习本 · AI出题</p>
    </div>
    """, unsafe_allow_html=True)

    # 知识库概览
    conn = sqlite3.connect(MEMORY_DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM user_knowledge WHERE user_id=?", (user_id,))
    total_knowledge = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM user_wrong_questions WHERE user_id=? AND status='active'", (user_id,))
    total_wrong = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(DISTINCT subject) FROM user_knowledge WHERE user_id=?", (user_id,))
    total_subjects = c.fetchone()[0] or 0
    conn.close()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("知识点", total_knowledge)
    with col2:
        st.metric("错题", total_wrong)
    with col3:
        st.metric("学科", total_subjects)

    st.markdown("---")

    tab_kb, tab_wrong, tab_review, tab_quiz = st.tabs([
        "📖 知识库", "📝 错题本", "📚 复习本", "🎲 AI出题"
    ])

    subjects_kb = ["数据结构", "计算机网络", "操作系统", "计算机组成", "其他"]

    # ── Tab 1: 知识库 ──
    with tab_kb:
        st.subheader("📖 知识库")
        selected_subject = st.selectbox("选择学科", subjects_kb, key="kb_subject")
        st.markdown("---")

        st.info("""
**上传说明：**
- 建议上传单个 PDF/图片，内容控制在 **50 页以内**
- 每个 PDF 代表一个大章节，请在下方命名
- 支持 PDF、PNG、JPG、TXT 格式
- 也支持直接粘贴文本资料
- 图片会优先使用 PaddleOCR 识别，不使用 AI 多模态识别
""")

        # 上传表单
        with st.form("upload_material"):
            chapter_name = st.text_input("章节名称", placeholder="例如：第一章 栈和队列")
            uploaded_file = st.file_uploader("上传资料", type=["pdf", "png", "jpg", "jpeg", "txt"], key="material_upload")
            pasted_text = st.text_area("或直接粘贴资料文本", height=180, placeholder="将课程讲义、笔记或整理后的原文粘贴到这里")
            if st.form_submit_button("上传并处理", use_container_width=True):
                if uploaded_file and pasted_text.strip():
                    st.warning("请在上传文件和粘贴文本之间选择一种输入方式。")
                elif chapter_name.strip() and (uploaded_file or pasted_text.strip()):
                    # 保存文件
                    file_path = ""
                    file_bytes = None
                    filename = "pasted_text.txt"
                    file_type = "pasted_text"
                    if uploaded_file:
                        user_dir = Path(f"data/user_materials/{user_id}")
                        user_dir.mkdir(parents=True, exist_ok=True)
                        file_path_obj = user_dir / uploaded_file.name
                        file_bytes = uploaded_file.getvalue()
                        file_path_obj.write_bytes(file_bytes)
                        file_path = str(file_path_obj)
                        filename = uploaded_file.name
                        file_type = uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else "unknown"

                    # 记录到数据库
                    conn = sqlite3.connect(MEMORY_DB)
                    c = conn.cursor()
                    c.execute("""INSERT INTO user_materials
                        (user_id, subject, filename, chapter_name, file_path, file_type, processing_status)
                        VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
                        (user_id, selected_subject, filename, chapter_name.strip(), file_path, file_type))
                    material_id = c.lastrowid
                    conn.commit()
                    conn.close()

                    spinner_text = "正在处理资料..."
                    if pasted_text.strip():
                        spinner_text = "正在整理粘贴文本..."
                    elif file_type == "pdf":
                        spinner_text = "正在解析 PDF，并按需回退 OCR..."
                    elif file_type in ("png", "jpg", "jpeg"):
                        spinner_text = "正在识别图片..."
                    elif file_type == "txt":
                        spinner_text = "正在整理 TXT 文本..."

                    with st.spinner(spinner_text):
                        material_result = route_material_input(
                            file_name=filename,
                            file_path=file_path,
                            file_bytes=file_bytes,
                            pasted_text=pasted_text,
                            image_ocr_fn=extract_text_from_image,
                            pdf_ocr_fn=extract_text_from_pdf_umiocr,
                            pdf_ocr_available=check_umiocr_available() if file_type == "pdf" else False,
                        )

                    st.session_state._material_result = material_result.to_dict()
                    _clear_current_draft_session()
                    st.session_state._ocr_preview = material_result.extracted_text
                    st.session_state._ocr_material_id = material_id
                    st.session_state._ocr_chapter = chapter_name.strip()
                    st.session_state._ocr_subject = selected_subject
                    st.session_state._ocr_file_type = file_type
                    st.session_state._ocr_filename = filename
                    st.rerun()

        # OCR 预览区域
        if st.session_state.get("_ocr_preview") is not None:
            ocr_text = st.session_state._ocr_preview
            material_id = st.session_state._ocr_material_id
            chapter_name = st.session_state._ocr_chapter
            selected_subject = st.session_state._ocr_subject
            file_type = st.session_state._ocr_file_type
            material_result = st.session_state.get("_material_result", {})

            st.markdown("---")
            st.subheader("📝 识别结果预览")

            st.caption(f"识别文字：{len(ocr_text)} 字 | 章节：{chapter_name}")
            if material_result:
                st.caption(
                    f"source_type: {material_result.get('source_type', 'unknown')} | "
                    f"process_method: {material_result.get('process_method', 'unknown')} | "
                    f"confidence: {material_result.get('confidence', 0.0):.2f}"
                )
                warnings = material_result.get("warnings") or []
                if warnings:
                    for warning in warnings:
                        st.warning(warning)

            edited_text = st.text_area(
                "识别结果（可编辑，修正识别错误后点击确认）",
                value=ocr_text[:5000],
                height=min(300, 250),
                key="ocr_edit_area"
            )

            col_confirm, col_retry = st.columns([3, 1])
            with col_confirm:
                if st.button("✅ 确认归纳知识点", use_container_width=True, type="primary"):
                    if edited_text.strip():
                        try:
                            drafts, draft_warnings = _extract_drafts_with_progress(
                                text=edited_text,
                                subject=selected_subject,
                                chapter_name=chapter_name,
                                max_points=12,
                            )
                            _set_draft_session_data(
                                [knowledge_point_to_dict(point) for point in drafts],
                                draft_warnings,
                            )
                            if drafts:
                                st.success(f"✅ 已生成 {len(drafts)} 条结构化知识点草稿。现在可以逐条编辑、删除、确认。")
                            else:
                                st.warning("未能生成有效的结构化知识点草稿，请减少文本长度或重新生成。")
                        except Exception as e:
                            st.warning(f"AI 处理失败：{e}")
                    else:
                        st.warning("识别结果为空，无法归纳")
            with col_retry:
                if st.button("🔄 重新上传", use_container_width=True):
                    del st.session_state._ocr_preview
                    del st.session_state._ocr_material_id
                    del st.session_state._ocr_chapter
                    del st.session_state._ocr_subject
                    del st.session_state._ocr_file_type
                    if "_ocr_filename" in st.session_state:
                        del st.session_state._ocr_filename
                    if "_material_result" in st.session_state:
                        del st.session_state._material_result
                    _clear_current_draft_session()
                    st.rerun()

            draft_points = st.session_state.get("knowledge_drafts") or []
            draft_warnings = st.session_state.get("knowledge_draft_warnings") or []
            confirmed_drafts = st.session_state.get("confirmed_knowledge_drafts") or []
            deleted_count = st.session_state.get("deleted_knowledge_draft_count", 0)
            persisted_ids = set(st.session_state.get("persisted_confirmed_knowledge_ids") or [])
            if draft_points:
                st.markdown("---")
                st.subheader("🧩 候选知识点草稿确认区")
                st.info("请先逐条核对 AI 或本地兜底生成的候选草稿。确认后的草稿会暂存在当前会话中，可在下方点击保存写入私有知识库。")
                if draft_warnings:
                    for warning in draft_warnings:
                        st.warning(warning)

                warning_count = sum(1 for point in draft_points if validate_required_fields(point))
                s1, s2, s3, s4 = st.columns(4)
                with s1:
                    st.metric("当前草稿", len(draft_points))
                with s2:
                    st.metric("已确认", len(confirmed_drafts))
                with s3:
                    st.metric("已删除", deleted_count)
                with s4:
                    st.metric("有警告", warning_count)

                action_col1, action_col2 = st.columns(2)
                with action_col1:
                    if st.button("✅ 确认全部剩余草稿", use_container_width=True, key="confirm_all_drafts"):
                        _confirm_all_drafts_in_session()
                        st.success("已将当前剩余草稿加入本次已确认知识点。")
                        st.rerun()
                with action_col2:
                    if st.button("🗑️ 清空本次草稿", use_container_width=True, key="clear_all_drafts"):
                        _clear_current_draft_session()
                        st.success("已清空本次草稿与本次已确认知识点。")
                        st.rerun()

                for idx, point in enumerate(draft_points, start=1):
                    title = point.get("knowledge_name") or f"未命名知识点 {idx}"
                    ktype = point.get("knowledge_type") or "未标注类型"
                    draft_id = point.get("_draft_id") or str(uuid4().hex)
                    point_warnings = validate_required_fields(point)
                    with st.expander(f"{idx}. {title} | {ktype}"):
                        if point_warnings:
                            for warning in point_warnings:
                                st.warning(warning)

                        st.text_input("knowledge_name", value=point.get("knowledge_name", ""), key=_draft_widget_key(draft_id, "knowledge_name"))
                        st.text_input("knowledge_type", value=point.get("knowledge_type", ""), key=_draft_widget_key(draft_id, "knowledge_type"))
                        st.text_input("subject", value=point.get("subject", ""), key=_draft_widget_key(draft_id, "subject"))
                        st.text_input("chapter_name", value=point.get("chapter_name", ""), key=_draft_widget_key(draft_id, "chapter_name"))
                        st.text_area("core_definition", value=point.get("core_definition", ""), key=_draft_widget_key(draft_id, "core_definition"), height=100)
                        st.text_area("exam_question_styles（逗号分隔）", value=_list_field_to_text(point.get("exam_question_styles")), key=_draft_widget_key(draft_id, "exam_question_styles"), height=70)
                        st.text_area("keywords（逗号分隔）", value=_list_field_to_text(point.get("keywords")), key=_draft_widget_key(draft_id, "keywords"), height=70)
                        st.text_area("related_concepts（逗号分隔）", value=_list_field_to_text(point.get("related_concepts")), key=_draft_widget_key(draft_id, "related_concepts"), height=70)
                        st.text_area("pitfalls（逗号分隔）", value=_list_field_to_text(point.get("pitfalls")), key=_draft_widget_key(draft_id, "pitfalls"), height=70)
                        st.text_area("example_or_application", value=point.get("example_or_application", ""), key=_draft_widget_key(draft_id, "example_or_application"), height=90)
                        st.selectbox("review_priority", ["低", "中", "高"], index=["低", "中", "高"].index(point.get("review_priority")) if point.get("review_priority") in ["低", "中", "高"] else 1, key=_draft_widget_key(draft_id, "review_priority"))
                        st.text_area("source_text", value=point.get("source_text", ""), key=_draft_widget_key(draft_id, "source_text"), height=120)
                        st.text_input("source_page", value=point.get("source_page", ""), key=_draft_widget_key(draft_id, "source_page"))
                        st.text_input("source_location", value=point.get("source_location", ""), key=_draft_widget_key(draft_id, "source_location"))
                        st.text_area("tags（逗号分隔）", value=_list_field_to_text(point.get("tags")), key=_draft_widget_key(draft_id, "tags"), height=70)
                        st.selectbox("mastery_state", ["待复习", "学习中", "已掌握"], index=["待复习", "学习中", "已掌握"].index(point.get("mastery_state")) if point.get("mastery_state") in ["待复习", "学习中", "已掌握"] else 0, key=_draft_widget_key(draft_id, "mastery_state"))
                        st.checkbox("is_ai_expansion", value=bool(point.get("is_ai_expansion")), key=_draft_widget_key(draft_id, "is_ai_expansion"))
                        st.text_area("uncertainty_note", value=point.get("uncertainty_note", ""), key=_draft_widget_key(draft_id, "uncertainty_note"), height=80)

                        b1, b2, b3 = st.columns(3)
                        with b1:
                            if st.button("💾 保存修改", key=f"save_draft_{draft_id}", use_container_width=True):
                                updated_point = _build_draft_from_widget(draft_id, point)
                                _replace_draft_in_session(updated_point)
                                st.success("已保存该条草稿修改。")
                                st.rerun()
                        with b2:
                            if st.button("🗑️ 删除该条", key=f"delete_draft_{draft_id}", use_container_width=True):
                                _remove_draft_from_session(draft_id)
                                st.success("已删除该条草稿。")
                                st.rerun()
                        with b3:
                            if st.button("✅ 确认该条", key=f"confirm_draft_{draft_id}", use_container_width=True):
                                updated_point = _build_draft_from_widget(draft_id, point)
                                _confirm_draft_in_session(updated_point)
                                st.success("已确认该条草稿，当前仅保存在会话中。")
                                st.rerun()
            elif draft_warnings or confirmed_drafts:
                st.markdown("---")
                st.subheader("🧩 候选知识点草稿确认区")
                st.info("请先逐条核对候选草稿。确认后的草稿会暂存在当前会话中，可在下方点击保存写入私有知识库。")
                for warning in draft_warnings:
                    st.warning(warning)

            if confirmed_drafts:
                st.markdown("---")
                st.subheader("✅ 本次已确认知识点")
                unsaved_confirmed = [point for point in confirmed_drafts if point.get("_draft_id") not in persisted_ids]
                save_col1, save_col2 = st.columns([3, 2])
                with save_col1:
                    if st.button("💾 保存已确认知识点到私有知识库", use_container_width=True, key="persist_confirmed_knowledge"):
                        if not unsaved_confirmed:
                            st.warning("暂无已确认知识点可保存。")
                        else:
                            conn = sqlite3.connect(MEMORY_DB)
                            try:
                                material_meta = {
                                    "material_id": material_id,
                                    "subject": selected_subject,
                                    "chapter_name": chapter_name,
                                    "source_type": material_result.get("source_type", "") if material_result else "",
                                    "process_method": material_result.get("process_method", "") if material_result else "",
                                    "material_filename": st.session_state.get("_ocr_filename", ""),
                                }
                                saved_count = save_confirmed_knowledge_points(
                                    conn,
                                    user_id,
                                    unsaved_confirmed,
                                    material_meta=material_meta,
                                )
                                conn.commit()
                                st.session_state["persisted_knowledge_count"] = saved_count
                                st.session_state["last_persisted_knowledge_names"] = [
                                    point.get("knowledge_name", "") for point in unsaved_confirmed
                                ]
                                st.session_state["persisted_confirmed_knowledge_ids"] = list(
                                    persisted_ids.union({point.get("_draft_id") for point in unsaved_confirmed})
                                )
                                _update_current_task("saved", note=f"已保存 {saved_count} 条知识点")
                                st.success(f"已保存 {saved_count} 条知识点到私有知识库。")
                                st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"保存失败：{e}")
                            finally:
                                conn.close()
                with save_col2:
                    st.caption(f"待保存确认项：{len(unsaved_confirmed)}")

                if st.session_state.get("persisted_knowledge_count"):
                    st.caption(
                        f"最近一次已保存 {st.session_state.get('persisted_knowledge_count', 0)} 条："
                        f"{'、'.join(st.session_state.get('last_persisted_knowledge_names') or [])}"
                    )

                for idx, point in enumerate(confirmed_drafts, start=1):
                    title = point.get("knowledge_name") or f"已确认知识点 {idx}"
                    ktype = point.get("knowledge_type") or "未标注类型"
                    with st.expander(f"{idx}. {title} | {ktype}"):
                        if point.get("_draft_id") in persisted_ids:
                            st.caption("已保存到私有知识库")
                        else:
                            st.caption("尚未保存到私有知识库")
                        st.markdown(f"**核心定义**：{point.get('core_definition') or '未提取'}")
                        st.markdown(f"**原文依据**：{point.get('source_text') or '未提取'}")
                        st.markdown(f"**标签**：{', '.join(point.get('tags') or []) or '未提取'}")

        # 已上传资料列表
        st.markdown("---")
        st.subheader("已上传资料")
        materials = get_user_materials(user_id, selected_subject)
        if materials:
            for mat in materials:
                status_icon = "✅" if mat[3] == "done" else "🔄" if mat[3] == "processing" else "⏳"
                with st.expander(f"{status_icon} {mat[2]} — {mat[1]} ({mat[4]}个知识点)"):
                    st.caption(f"文件：{mat[1]} | 状态：{mat[3]} | 知识点：{mat[4]}个")
        else:
            st.info("暂无上传资料，请先上传。")

        # 知识点列表
        st.markdown("---")
        st.subheader("知识点列表")
        knowledge_items = get_user_knowledge(user_id, selected_subject)
        if knowledge_items:
            current_chapter = ""
            for item in knowledge_items:
                if item[0] != current_chapter:
                    current_chapter = item[0]
                    st.markdown(f"### 📖 {current_chapter}")
                with st.expander(f"📌 {item[1]}"):
                    st.markdown(item[2][:1000])
        else:
            st.info("暂无知识点，请先上传资料。")

    # ── Tab 2: 错题本 ──
    with tab_wrong:
        st.subheader("📝 错题本")
        wrong_subject = st.selectbox("选择学科", subjects_kb, key="wrong_subject")
        wrong_questions = get_user_wrong_questions(user_id, wrong_subject)

        if wrong_questions:
            for wq in wrong_questions:
                with st.expander(f"❌ {wq[2][:50]}... (错{wq[6]}次)"):
                    st.markdown(f"**题目**: {wq[2]}")
                    st.markdown(f"**你的答案**: {wq[3]}")
                    st.markdown(f"**正确答案**: {wq[4]}")
                    st.markdown(f"**解析**: {wq[5]}")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ 标记已掌握", key=f"wrong_{wq[0]}"):
                            mark_wrong_mastered(wq[0])
                            st.rerun()
                    with c2:
                        if st.button("🔄 重新学习", key=f"relearn_{wq[0]}"):
                            relearn_wrong(wq[0])
                            st.rerun()
        else:
            st.info("🎉 当前学科没有错题！")

        st.markdown("---")
        st.subheader("添加错题")
        with st.form("add_wrong_question"):
            wq_question = st.text_area("题目", placeholder="输入题目内容")
            wq_user_answer = st.text_input("你的答案", placeholder="你的错误答案")
            wq_correct = st.text_input("正确答案", placeholder="正确答案")
            wq_explain = st.text_area("解析", placeholder="解析说明")
            if st.form_submit_button("添加", use_container_width=True):
                if wq_question and wq_correct:
                    add_wrong_question(user_id, wrong_subject, wq_question, wq_user_answer, wq_correct, wq_explain)
                    st.success("✅ 错题已添加！")
                    st.rerun()

    # ── Tab 3: 复习本 ──
    with tab_review:
        st.subheader("📚 复习本")
        review_subject = st.selectbox("选择学科", subjects_kb, key="review_subject")
        review_items = get_review_items(user_id, review_subject)

        if review_items:
            st.markdown(f"**待复习知识点（{len(review_items)}个）：**")
            for item in review_items:
                with st.expander(f"📌 {item[0]} — {item[1][:30]}"):
                    st.markdown(f"**题目**: {item[1]}")
                    st.markdown(f"**解析**: {item[2]}")
                    st.caption(f"上次复习: {item[3] or '从未'}")
        else:
            st.info("🎉 当前学科没有待复习的知识点！")

    # ── Tab 4: AI出题 ──
    with tab_quiz:
        st.subheader("🎲 AI出题")
        quiz_subject = st.selectbox("选择学科", subjects_kb, key="quiz_subject")

        conn = sqlite3.connect(MEMORY_DB)
        c = conn.cursor()
        c.execute("SELECT DISTINCT knowledge_name FROM user_knowledge WHERE user_id=? AND subject=?",
                 (user_id, quiz_subject))
        quiz_knowledge = [row[0] for row in c.fetchall()]
        conn.close()

        if quiz_knowledge:
            selected_knowledge = st.selectbox("选择知识点", quiz_knowledge, key="quiz_knowledge")
            if st.button("🎲 生成练习题", use_container_width=True):
                with st.spinner("正在生成..."):
                    try:
                        quiz_prompt = f"""你是考研数学辅导专家。请根据知识点「{selected_knowledge}」出1道练习题。

输出格式（严格遵守）：
Q: 题目（用文字描述，不要用LaTeX公式）
A) 选项A
B) 选项B
C) 选项C
D) 选项D
ANSWER: 正确选项
EXPLAIN: 解析"""
                        result = _call_llm_api(quiz_prompt, model="mimo-v2.5", max_tokens=1000)
                        st.markdown("---")
                        st.markdown("### 生成结果")
                        st.markdown(result)
                    except Exception as e:
                        st.error(f"生成失败: {e}")
        else:
            st.info("暂无知识点，请先在知识库中上传资料。")


# ==================== 新版简化 UI 渲染 ====================

def _render_draft_editor(point, idx):
    title = point.get("knowledge_name") or f"候选知识点 {idx}"
    ktype = point.get("knowledge_type") or "未标注类型"
    draft_id = point.get("_draft_id") or str(uuid4().hex)
    point_warnings = validate_required_fields(point)
    st.markdown(
        f"""
        <div class="pk-section-heading">
            <h2>{idx}. {_escape_html(title)}</h2>
            <p>{_escape_html(ktype)} · 请核对核心定义、考法、原文依据和页码，确认后再写入私有知识库。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if point_warnings:
        st.warning("；".join(point_warnings))

    basic_tab, exam_tab, source_tab = st.tabs(["基础信息", "考法与标签", "来源与引用"])
    with basic_tab:
        st.text_input("知识点名称", value=point.get("knowledge_name", ""), key=_draft_widget_key(draft_id, "knowledge_name"))
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("类型", value=point.get("knowledge_type", ""), key=_draft_widget_key(draft_id, "knowledge_type"))
            st.text_input("学科", value=point.get("subject", ""), key=_draft_widget_key(draft_id, "subject"))
        with c2:
            st.text_input("章节", value=point.get("chapter_name", ""), key=_draft_widget_key(draft_id, "chapter_name"))
            st.selectbox(
                "复习优先级",
                ["低", "中", "高"],
                index=["低", "中", "高"].index(point.get("review_priority")) if point.get("review_priority") in ["低", "中", "高"] else 1,
                key=_draft_widget_key(draft_id, "review_priority"),
            )
        st.text_area("核心定义", value=point.get("core_definition", ""), key=_draft_widget_key(draft_id, "core_definition"), height=120)

    with exam_tab:
        st.text_area("常见考法", value=_list_field_to_text(point.get("exam_question_styles")), key=_draft_widget_key(draft_id, "exam_question_styles"), height=90)
        st.text_area("关键词", value=_list_field_to_text(point.get("keywords")), key=_draft_widget_key(draft_id, "keywords"), height=80)
        st.text_area("相关概念", value=_list_field_to_text(point.get("related_concepts")), key=_draft_widget_key(draft_id, "related_concepts"), height=80)
        st.text_area("易错点", value=_list_field_to_text(point.get("pitfalls")), key=_draft_widget_key(draft_id, "pitfalls"), height=80)
        st.text_area("例子 / 应用", value=point.get("example_or_application", ""), key=_draft_widget_key(draft_id, "example_or_application"), height=90)

    with source_tab:
        st.text_area("原文依据", value=point.get("source_text", ""), key=_draft_widget_key(draft_id, "source_text"), height=180)
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("页码", value=point.get("source_page", ""), key=_draft_widget_key(draft_id, "source_page"))
        with c2:
            st.text_input("位置", value=point.get("source_location", ""), key=_draft_widget_key(draft_id, "source_location"))
        st.text_area("标签", value=_list_field_to_text(point.get("tags")), key=_draft_widget_key(draft_id, "tags"), height=70)
        st.selectbox(
            "掌握状态",
            ["待复习", "学习中", "已掌握"],
            index=["待复习", "学习中", "已掌握"].index(point.get("mastery_state")) if point.get("mastery_state") in ["待复习", "学习中", "已掌握"] else 0,
            key=_draft_widget_key(draft_id, "mastery_state"),
        )
        st.checkbox("AI 发散内容", value=bool(point.get("is_ai_expansion")), key=_draft_widget_key(draft_id, "is_ai_expansion"))
        st.text_area("不确定说明", value=point.get("uncertainty_note", ""), key=_draft_widget_key(draft_id, "uncertainty_note"), height=90)

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("保存修改", key=f"save_draft_{draft_id}", use_container_width=True):
            _replace_draft_in_session(_build_draft_from_widget(draft_id, point))
            _persist_active_workflow_snapshot(status="drafted")
            st.success("已保存修改")
            st.rerun()
    with b2:
        if st.button("删除当前草稿", key=f"delete_draft_{draft_id}", use_container_width=True):
            _remove_draft_from_session(draft_id)
            _persist_active_workflow_snapshot(status="drafted")
            st.rerun()
    with b3:
        if st.button("确认并加入待保存", key=f"confirm_draft_{draft_id}", use_container_width=True, type="primary"):
            _confirm_draft_in_session(_build_draft_from_widget(draft_id, point))
            _persist_active_workflow_snapshot(status="drafted")
            st.rerun()


def _render_confirmed_panel(user_id, selected_subject, chapter_name, material_id, material_result):
    confirmed_drafts = st.session_state.get("confirmed_knowledge_drafts") or []
    if not confirmed_drafts:
        st.markdown(
            """
            <div class="pk-empty-state">
                当前还没有已确认知识点。左侧核对候选草稿后，确认项会先进入这里，再统一保存到私有知识库。
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    persisted_ids = set(st.session_state.get("persisted_confirmed_knowledge_ids") or [])
    unsaved_confirmed = [point for point in confirmed_drafts if point.get("_draft_id") not in persisted_ids]
    invalid_confirmed = []
    for point in unsaved_confirmed:
        point_warnings = validate_required_fields(point)
        if point_warnings:
            invalid_confirmed.append((point, point_warnings))
    _render_info_card(
        "待保存知识点",
        "这里只有用户已经确认的知识点会被保存。AI 扩展内容会按字段单独标记，不会伪装成原文事实。",
        metrics=[
            ("待保存", len(unsaved_confirmed)),
            ("总确认数", len(confirmed_drafts)),
            ("已入库", len(confirmed_drafts) - len(unsaved_confirmed)),
            ("来源章节", chapter_name or "未填写"),
        ],
        badges=[
            (selected_subject or "未分类学科", ""),
            ((material_result or {}).get("process_method", "unknown"), ""),
        ],
        kicker="待保存区",
    )
    st.info("只有用户确认的知识点才会保存。AI 扩展内容必须标记，不得伪装成原文事实。")
    if invalid_confirmed:
        invalid_names = "、".join(
            (point.get("knowledge_name") or "未命名知识点")
            for point, _warnings in invalid_confirmed[:5]
        )
        st.error(
            f"有 {len(invalid_confirmed)} 条知识点缺少名称、核心定义或原文依据，暂不能入库：{invalid_names}。"
            "请先移回候选区补全。"
        )

    action_left, action_right = st.columns(2)
    with action_left:
        if st.button("全部移回候选区", use_container_width=True, key="restore_all_confirmed_v2"):
            restored_any = False
            for point in reversed(list(unsaved_confirmed)):
                draft_id = point.get("_draft_id")
                if draft_id and _restore_confirmed_draft_to_queue(draft_id):
                    restored_any = True
            if restored_any:
                _persist_active_workflow_snapshot(status="drafted")
                st.rerun()
    with action_right:
        if st.button("清空待保存区", use_container_width=True, key="clear_confirmed_v2"):
            for point in list(unsaved_confirmed):
                _remove_confirmed_draft_from_session(point.get("_draft_id"))
            if unsaved_confirmed:
                _persist_active_workflow_snapshot(status="drafted")
                st.rerun()

    if st.button(
        "保存已确认知识点到私有知识库",
        use_container_width=True,
        type="primary",
        key="persist_confirmed_knowledge_v2",
        disabled=bool(invalid_confirmed),
    ):
        if not unsaved_confirmed:
            st.warning("暂无待保存知识点。")
        else:
            conn = sqlite3.connect(MEMORY_DB)
            try:
                subject_profile = get_rag_knowledge_base_by_subject(selected_subject)
                material_meta = {
                    "material_id": material_id,
                    "subject": selected_subject,
                    "subject_key": subject_profile.key if subject_profile else "",
                    "chapter_name": chapter_name,
                    "source_type": material_result.get("source_type", "") if material_result else "",
                    "process_method": material_result.get("process_method", "") if material_result else "",
                    "material_filename": st.session_state.get("_ocr_filename", ""),
                }
                saved_count = save_confirmed_knowledge_points(
                    conn,
                    user_id,
                    unsaved_confirmed,
                    material_meta=material_meta,
                    strict=True,
                    finalize_material=False,
                )
                next_persisted_ids = persisted_ids.union(
                    {
                        point.get("_draft_id")
                        for point in unsaved_confirmed
                        if point.get("_draft_id")
                    }
                )
                snapshot = _build_active_workflow_snapshot()
                snapshot["persisted_draft_ids"] = list(next_persisted_ids)
                confirmed_ids = {
                    point.get("_draft_id")
                    for point in snapshot.get("confirmed_drafts") or []
                    if point.get("_draft_id")
                }
                workflow_complete = (
                    not snapshot.get("remaining_drafts")
                    and bool(confirmed_ids)
                    and confirmed_ids.issubset(next_persisted_ids)
                )
                if material_id:
                    save_workflow_snapshot(
                        conn,
                        material_id,
                        snapshot,
                        status="done" if workflow_complete else "drafted",
                    )
                conn.commit()
                st.session_state["persisted_knowledge_count"] = saved_count
                st.session_state["persisted_confirmed_knowledge_ids"] = list(next_persisted_ids)
                _update_current_task(
                    "saved" if workflow_complete else "drafted",
                    note=f"已保存 {saved_count} 条知识点",
                )
                skipped_count = max(0, len(unsaved_confirmed) - saved_count)
                if skipped_count:
                    st.success(f"已新增 {saved_count} 条知识点，自动跳过 {skipped_count} 条重复内容")
                else:
                    st.success(f"已保存 {saved_count} 条知识点")
                st.rerun()
            except Exception as e:
                conn.rollback()
                st.error(f"保存失败：{e}")
            finally:
                conn.close()

    for idx, point in enumerate(confirmed_drafts, start=1):
        title = point.get("knowledge_name") or "未命名知识点"
        is_persisted = point.get("_draft_id") in persisted_ids
        point_status = "已保存" if is_persisted else "待保存"
        point_type = point.get("knowledge_type") or "未标注类型"
        with st.expander(f"{idx}. {title} · {point_status} · {point_type}", expanded=False):
            st.caption(f"来源：{point.get('source_page') or '未知页码'} / {point.get('source_location') or '未知位置'}")
            st.write(point.get("core_definition") or "暂无定义")
            if point.get("source_text"):
                st.text_area(
                    "原文依据",
                    value=point.get("source_text", ""),
                    height=140,
                    key=f"confirmed_source_{point.get('_draft_id') or idx}",
                    disabled=True,
                )

            if is_persisted:
                st.caption("该条已写入私有知识库；如需修改，请在“我的知识库”中操作。")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("移回候选区", key=f"restore_confirmed_{point.get('_draft_id')}", use_container_width=True):
                        if _restore_confirmed_draft_to_queue(point.get("_draft_id")):
                            _persist_active_workflow_snapshot(status="drafted")
                            st.rerun()
                with c2:
                    if st.button("从待保存移除", key=f"remove_confirmed_{point.get('_draft_id')}", use_container_width=True):
                        _remove_confirmed_draft_from_session(point.get("_draft_id"))
                        _persist_active_workflow_snapshot(status="drafted")
                        st.rerun()


def _render_private_repository(user_id):
    conn = sqlite3.connect(MEMORY_DB)
    try:
        points = list_user_knowledge_points(conn, user_id, limit=200)
    finally:
        conn.close()

    if not points:
        st.markdown(
            """
            <div class="pk-empty-state">
                私有知识库为空。请先在“识别资料”中上传或粘贴资料，再到“确认入库”保存知识点。
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    total_points = len(points)
    subjects = ["全部"] + sorted({p.get("subject") or "未分类" for p in points})
    filter_col, search_col, count_col = st.columns([1.1, 2.2, 0.75])
    with filter_col:
        selected = st.selectbox("筛选学科", subjects, key="repo_subject_filter")
    if selected != "全部":
        points = [p for p in points if (p.get("subject") or "未分类") == selected]

    with search_col:
        search_query = st.text_input(
            "搜索知识点",
            placeholder="输入知识点、关键词、原文依据或复习内容",
            key="repo_search_query",
        ).strip()
    if search_query:
        points = _filter_repository_points(points, search_query)

    with count_col:
        st.metric("显示", len(points), delta=f"共 {total_points}", delta_color="off")

    st.markdown(
        '<div class="pk-toolbar-note">筛选和搜索会同时作用于当前私有知识库，复习内容生成后会保留在对应知识点内。</div>',
        unsafe_allow_html=True,
    )
    if not points:
        st.markdown(
            """
            <div class="pk-empty-state">
                没有找到匹配的知识点。可以换一个关键词，或回到“识别资料”继续入库。
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    point_map = {str(point.get("id")): point for point in points if point.get("id") is not None}
    point_ids = list(point_map.keys())
    selected_id = st.session_state.get("repo_selected_id")
    if selected_id not in point_map:
        selected_id = point_ids[0]
        st.session_state["repo_selected_id"] = selected_id

    left_col, right_col = st.columns([1, 1.4])
    with left_col:
        _render_info_card(
            "知识点列表",
            "左侧负责筛选和切换当前知识点，右侧展示原文依据、状态和复习内容。",
            metrics=[
                ("当前显示", len(points)),
                ("总知识点", total_points),
                ("学科过滤", selected),
                ("搜索词", search_query or "无"),
            ],
            kicker="知识工作台",
        )
        selected_id = st.radio(
            "知识点列表",
            options=point_ids,
            index=point_ids.index(selected_id),
            format_func=lambda point_id: _format_repo_option(point_map[point_id]),
            key="repo_selected_id",
            label_visibility="collapsed",
        )

    point = point_map[selected_id]
    with right_col:
        title = point.get("knowledge_name") or "未命名知识点"
        _render_info_card(
            title,
            point.get("core_definition") or point.get("content") or "暂无内容",
            metrics=[
                ("学科", point.get("subject") or "未分类"),
                ("章节", point.get("chapter_name") or "未标注"),
                ("页码", point.get("source_page") or "未知"),
                ("状态", point.get("mastery_state") or "待复习"),
            ],
            badges=[
                (point.get("knowledge_type") or "知识点", ""),
                (point.get("source_location") or "未标注位置", ""),
            ],
            kicker="当前知识点",
        )

        if point.get("source_text"):
            st.text_area(
                "原文依据",
                value=point.get("source_text"),
                height=min(320, max(150, len(point.get("source_text") or "") // 2)),
                key=f"source_text_view_{point.get('id')}",
                disabled=True,
            )

        c1, c2, c3 = st.columns(3)
        stored_expansion = point.get("review_content") or st.session_state.get(f"expansion_{point.get('id')}")
        generate_label = "重新生成复习内容" if stored_expansion else "生成复习内容"
        with c1:
            if st.button("标记学习中", key=f"learning_{point.get('id')}", use_container_width=True):
                _update_knowledge_mastery(point.get("id"), "学习中")
                st.rerun()
        with c2:
            if st.button("标记已掌握", key=f"mastered_{point.get('id')}", use_container_width=True):
                _update_knowledge_mastery(point.get("id"), "已掌握")
                st.rerun()
        with c3:
            if st.button(generate_label, key=f"expand_{point.get('id')}", use_container_width=True):
                with st.spinner("正在生成复习内容..."):
                    try:
                        expansion = generate_review_expansion(point)
                        _save_review_expansion(point.get("id"), expansion)
                        st.session_state[f"expansion_{point.get('id')}"] = expansion
                        st.success("复习内容已保存")
                    except Exception as exc:
                        st.session_state[f"expansion_{point.get('id')}"] = f"生成失败：{exc}"

        expansion = point.get("review_content") or st.session_state.get(f"expansion_{point.get('id')}")
        if expansion:
            st.markdown("**AI 复习内容**")
            if point.get("review_generated_at"):
                st.caption(f"生成时间：{point.get('review_generated_at')}")
            st.markdown(expansion)
        else:
            st.markdown(
                """
                <div class="pk-empty-state">
                    这条知识点还没有复习内容。确认原文依据无误后，可以在上方生成复习扩展。
                </div>
                """,
                unsafe_allow_html=True,
            )


def _filter_repository_points(points, query):
    query = (query or "").strip().lower()
    if not query:
        return points

    matched = []
    searchable_fields = [
        "knowledge_name",
        "knowledge_type",
        "subject",
        "chapter_name",
        "core_definition",
        "content",
        "source_text",
        "source_page",
        "source_location",
        "tags_json",
        "keywords_json",
        "review_content",
    ]
    for point in points:
        haystack = "\n".join(str(point.get(field) or "") for field in searchable_fields).lower()
        if query in haystack:
            matched.append(point)
    return matched


def _save_review_expansion(knowledge_id, expansion):
    if not knowledge_id:
        return
    conn = sqlite3.connect(MEMORY_DB)
    try:
        update_knowledge_review_content(conn, knowledge_id, expansion)
        conn.commit()
    finally:
        conn.close()


def _is_local_user_material_path(file_path):
    if not file_path:
        return False
    try:
        path = Path(file_path).resolve()
        root = Path("data/user_materials").resolve()
        return path == root or root in path.parents
    except Exception:
        return False


def _remove_local_material_file(file_path):
    if not _is_local_user_material_path(file_path):
        return
    try:
        path = Path(file_path)
        if path.exists() and path.is_file():
            path.unlink()
    except Exception:
        return


def _discard_material_if_unsaved(material_id):
    if not material_id:
        return
    conn = sqlite3.connect(MEMORY_DB)
    try:
        row = conn.execute(
            """SELECT id, file_path FROM user_materials
               WHERE id=? AND COALESCE(knowledge_count, 0)=0
                 AND NOT EXISTS (
                     SELECT 1 FROM user_knowledge
                     WHERE user_knowledge.material_id=user_materials.id
                 )""",
            (material_id,),
        ).fetchone()
        if row:
            _remove_local_material_file(row[1])
            conn.execute("DELETE FROM user_materials WHERE id=?", (material_id,))
            conn.commit()
    finally:
        conn.close()


def _count_effective_materials(c, user_id):
    return c.execute(
        """SELECT COUNT(*)
           FROM user_materials
           WHERE user_id=?
             AND (
                 COALESCE(knowledge_count, 0)>0
                 OR processing_status='done'
                 OR EXISTS (
                     SELECT 1 FROM user_knowledge
                     WHERE user_knowledge.material_id=user_materials.id
                 )
             )""",
        (user_id,),
    ).fetchone()[0] or 0


_ACTIVE_MATERIAL_STATE_KEYS = [
    "_ocr_preview",
    "_ocr_material_id",
    "_ocr_chapter",
    "_ocr_subject",
    "_ocr_file_type",
    "_ocr_filename",
    "_material_result",
    "_pk_task_id",
]


def _sanitize_material_filename(filename):
    safe_name = Path(filename or "").name.strip()
    if safe_name:
        return safe_name
    return f"material-{uuid4().hex}.txt"


def _infer_material_file_type(filename, default="pasted_text"):
    suffix = Path(filename or "").suffix.lower()
    if not suffix:
        return default
    return suffix.lstrip(".")


def _persist_user_material_file(user_id, filename, file_bytes):
    if not file_bytes:
        return ""

    user_dir = Path(f"data/user_materials/{user_id}")
    user_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_material_filename(filename)
    target = user_dir / safe_name
    if target.exists():
        target = user_dir / f"{target.stem}-{uuid4().hex[:8]}{target.suffix}"
    target.write_bytes(file_bytes)
    return str(target)


def _clear_active_material_state(*, discard_unsaved=False):
    if discard_unsaved:
        _discard_material_if_unsaved(st.session_state.get("_ocr_material_id"))
    for key in _ACTIVE_MATERIAL_STATE_KEYS:
        st.session_state.pop(key, None)


def _set_active_material_state(*, material_id, chapter_name, subject, file_type, filename, material_result):
    st.session_state.pop("ocr_raw_area_v2", None)
    st.session_state.pop("ocr_edit_area_v2", None)
    st.session_state["_material_result"] = material_result.to_dict()
    _clear_current_draft_session()
    st.session_state["_ocr_preview"] = material_result.extracted_text
    st.session_state["_ocr_material_id"] = material_id
    st.session_state["_ocr_chapter"] = chapter_name
    st.session_state["_ocr_subject"] = subject
    st.session_state["_ocr_file_type"] = file_type
    st.session_state["_ocr_filename"] = filename


def _process_material_submission(
    *,
    user_id,
    subject,
    chapter_name,
    filename,
    file_bytes=None,
    pasted_text="",
    open_preview=True,
    rerun_on_complete=True,
):
    safe_filename = _sanitize_material_filename(filename)
    clean_chapter_name = (chapter_name or "").strip()
    file_type = _infer_material_file_type(safe_filename)
    file_path = _persist_user_material_file(user_id, safe_filename, file_bytes) if file_bytes else ""
    subject_profile = get_rag_knowledge_base_by_subject(subject)
    subject_key = subject_profile.key if subject_profile else ""
    source_bytes = file_bytes if file_bytes else (pasted_text or "").encode("utf-8")
    source_hash = hashlib.sha256(source_bytes).hexdigest() if source_bytes else ""

    conn = sqlite3.connect(MEMORY_DB)
    try:
        material_record = create_material(
            conn,
            user_id=user_id,
            subject=subject,
            subject_key=subject_key,
            filename=safe_filename,
            chapter_name=clean_chapter_name,
            file_path=file_path,
            file_type=file_type,
            content_hash=source_hash,
            processing_status="pending",
        )
        material_id = material_record["id"]
        conn.commit()
    except Exception as exc:
        conn.rollback()
        _remove_local_material_file(file_path)
        st.error(f"无法创建资料记录：{exc}")
        return {
            "material_id": None,
            "chapter_name": clean_chapter_name,
            "subject": subject,
            "file_type": file_type,
            "filename": safe_filename,
            "error": str(exc),
        }
    finally:
        conn.close()

    try:
        task = create_professional_task(
            user_id=user_id,
            subject=subject,
            chapter_name=clean_chapter_name,
            filename=safe_filename,
            material_id=material_id,
        )
    except Exception:
        task = None
    if task is not None:
        st.session_state["_pk_task_id"] = task.task_id
    else:
        st.session_state.pop("_pk_task_id", None)

    status_label = "正在识别资料..."
    if file_type == "pdf":
        status_label = "正在检查 PDF 结构..."
    elif file_type in {"png", "jpg", "jpeg"}:
        status_label = "正在识别图片文字..."
    elif pasted_text.strip():
        status_label = "正在清洗粘贴文本..."

    processing_status = st.status(status_label, expanded=True)
    processing_progress = st.progress(0)

    def update_ocr_progress(current, total, message):
        progress_value = current / max(total, 1)
        processing_progress.progress(min(progress_value, 1.0))
        processing_status.update(label=message, state="running")

    try:
        with processing_status:
            material_result = route_material_input(
                file_name=safe_filename,
                file_path=file_path,
                file_bytes=file_bytes,
                pasted_text=pasted_text,
                image_ocr_fn=extract_text_from_image,
                pdf_ocr_fn=lambda path: extract_text_from_pdf_paddleocr(
                    path,
                    progress_callback=update_ocr_progress,
                ),
                pdf_ocr_available=(is_rapid_ocr_available() or is_paddle_ocr_available()) if file_type == "pdf" else False,
            )
    except Exception as exc:
        conn = sqlite3.connect(MEMORY_DB)
        try:
            mark_material_status(conn, material_id, "failed", error_message=str(exc))
            conn.commit()
        finally:
            conn.close()
        _update_current_task("failed", note=f"资料识别失败：{exc}")
        processing_status.update(label="资料识别失败", state="error", expanded=True)
        st.error(f"资料识别失败：{exc}")
        return {
            "material_id": material_id,
            "chapter_name": clean_chapter_name,
            "subject": subject,
            "file_type": file_type,
            "filename": safe_filename,
            "task_id": task.task_id if task is not None else "",
            "error": str(exc),
        }

    if file_type in {"png", "jpg", "jpeg"} and not (is_rapid_ocr_available() or is_paddle_ocr_available()):
        message = "OCR 服务不可用。文字型 PDF 仍可直接提取；扫描型 PDF 或图片可能无法识别。"
        if message not in material_result.warnings:
            material_result.warnings.append(message)

    conn = sqlite3.connect(MEMORY_DB)
    try:
        save_extraction_result(
            conn,
            material_id,
            material_result,
            status="extracted",
            content_hash=source_hash,
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        try:
            mark_material_status(conn, material_id, "failed", error_message=str(exc))
            conn.commit()
        except Exception:
            conn.rollback()
        _update_current_task("failed", note=f"保存资料提取结果失败：{exc}")
        processing_status.update(label="保存资料状态失败", state="error", expanded=True)
        st.error(f"资料已经识别，但保存恢复状态失败：{exc}")
        return {
            "material_id": material_id,
            "chapter_name": clean_chapter_name,
            "subject": subject,
            "file_type": file_type,
            "filename": safe_filename,
            "task_id": task.task_id if task is not None else "",
            "error": str(exc),
        }
    finally:
        conn.close()

    processing_progress.progress(1.0)
    processing_status.update(label="资料识别完成", state="complete", expanded=False)
    _update_current_task(
        "extracted",
        note="资料识别完成",
        source_type=material_result.source_type,
        process_method=material_result.process_method,
        warning_count=len(material_result.warnings or []),
    )

    if open_preview:
        _set_active_material_state(
            material_id=material_id,
            chapter_name=clean_chapter_name,
            subject=subject,
            file_type=file_type,
            filename=safe_filename,
            material_result=material_result,
        )
    engine = material_result.ocr_report.get("primary_engine")
    method_label = f"，主要引擎为 {engine}" if engine else ""
    _queue_toast(f"资料提取完成{method_label}")
    if rerun_on_complete:
        st.rerun()

    return {
        "material_id": material_id,
        "chapter_name": clean_chapter_name,
        "subject": subject,
        "file_type": file_type,
        "filename": safe_filename,
        "task_id": task.task_id if task is not None else "",
        "material_result": material_result,
    }


def _build_material_batch_chapter_name(chapter_name: str, filename: str, multi_file: bool) -> str:
    base = (chapter_name or "").strip()
    stem = Path(filename or "").stem
    if not base:
        return stem
    if multi_file:
        return f"{base} - {stem}"
    return base


def _process_material_batch_uploads(*, user_id, subject, chapter_name, uploaded_files) -> None:
    files = list(uploaded_files or [])
    if not files:
        st.warning("请上传至少一个文件。")
        return

    multi_file = len(files) > 1
    if multi_file and not (chapter_name or "").strip():
        st.warning("批量上传时请填写章节 / 文件主题，系统会自动拼接文件名生成每份资料的章节名。")
        return

    processed = 0
    failed = 0
    last_result = None
    for index, uploaded_file in enumerate(files, start=1):
        chapter_value = _build_material_batch_chapter_name(chapter_name, uploaded_file.name, multi_file)
        result = _process_material_submission(
            user_id=user_id,
            subject=subject,
            chapter_name=chapter_value,
            filename=uploaded_file.name,
            file_bytes=uploaded_file.getvalue(),
            open_preview=False,
            rerun_on_complete=False,
        )
        if result.get("error"):
            failed += 1
            continue
        processed += 1
        last_result = result

    if multi_file and processed:
        suffix = f"，{failed} 份失败并已保留错误状态" if failed else ""
        _queue_toast(f"已批量导入 {processed} 份资料{suffix}，当前打开最后一份继续确认。")
    if last_result:
        _set_active_material_state(
            material_id=last_result["material_id"],
            chapter_name=last_result["chapter_name"],
            subject=last_result["subject"],
            file_type=last_result["file_type"],
            filename=last_result["filename"],
            material_result=last_result["material_result"],
        )
        if last_result.get("task_id"):
            st.session_state["_pk_task_id"] = last_result["task_id"]
        st.rerun()


def _format_file_size(size_bytes):
    value = float(size_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}GB"


def _format_local_material_option(item):
    return f"{item['relative_path']} · {_format_file_size(item.get('size_bytes', 0))}"


def _guess_chapter_name_from_relative_path(relative_path):
    path = Path(relative_path or "")
    if not relative_path:
        return ""
    if len(path.parts) >= 2:
        return f"{path.parts[-2]} - {path.stem}"
    return path.stem


def _render_rag_knowledge_base_catalog():
    items = list_rag_knowledge_bases()
    if not items:
        return

    card_html = []
    for item in items:
        status_class = "kb-card-status active" if item.enabled else "kb-card-status"
        card_class = "kb-catalog-card active" if item.enabled else "kb-catalog-card"
        tags = "".join(
            f'<span class="kb-card-tag">{_escape_html(tag)}</span>'
            for tag in item.capabilities[:3]
        )
        card_html.append(
            (
                f'<div class="{card_class}">'
                f'<div class="kb-card-top">'
                f'<div class="kb-card-title">{_escape_html(item.title)}</div>'
                f'<div class="{status_class}">{_escape_html(item.status)}</div>'
                f"</div>"
                f'<div class="kb-card-stage">{_escape_html(item.stage)} · {_escape_html(item.subject_label)}</div>'
                f'<div class="kb-card-summary">{_escape_html(item.summary)}</div>'
                f'<div class="kb-card-tags">{tags}</div>'
                f"</div>"
            )
        )

    st.markdown(
        (
            '<div class="pk-section-heading">'
            "<h2>专业课 RAG 知识库</h2>"
            "<p>当前已启用 408 与医学考研，后续小众专业课按统一框架继续扩展。</p>"
            "</div>"
            '<div class="kb-catalog">'
            f'<div class="kb-catalog-grid">{"".join(card_html)}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_subject_setup_wizard():
    with st.expander("＋ 新建一门专业课知识库", expanded=False):
        st.caption("只填专业课名称就能使用；考试代码、资料文件夹和抽取重点都可以留空，之后再补。")
        with st.form("create_custom_subject_v1"):
            subject_label = st.text_input("专业课名称 *", placeholder="例如：管理学原理")
            exam_code = st.text_input("考试代码（可选）", placeholder="例如：803")
            local_root = st.text_input(
                "本地资料文件夹（可选）",
                placeholder=r"例如：D:\考研资料\803管理学",
            )
            extraction_guidance = st.text_area(
                "希望系统重点识别什么（可选）",
                placeholder="例如：优先识别理论流派、代表人物、核心观点、适用条件和易混点。",
                height=90,
            )
            submitted = st.form_submit_button("创建并开始导入资料", use_container_width=True, type="primary")

        if not submitted:
            return
        clean_label = subject_label.strip()
        if not clean_label:
            st.warning("请先填写专业课名称。")
            return
        existing_profile = get_rag_knowledge_base_by_subject(clean_label)
        if existing_profile is not None:
            st.session_state["_pending_kb_subject"] = clean_label
            _queue_toast(f"“{clean_label}”已经存在，已为你选中")
            st.rerun()

        resolved_root = ""
        if local_root.strip():
            candidate = Path(local_root.strip()).expanduser()
            if not candidate.exists() or not candidate.is_dir():
                st.warning("本地资料文件夹不存在，请检查路径；也可以先留空，创建后直接上传资料。")
                return
            resolved_root = str(candidate.resolve())

        profile_key = f"custom_{uuid4().hex[:10]}"
        clean_code = exam_code.strip()
        title = f"{clean_code} {clean_label}".strip()
        local_source = None
        if resolved_root:
            local_source = {
                "key": profile_key,
                "title": f"本地{clean_label}资料",
                "tab_label": "本地资料库",
                "root_env_var": f"{profile_key.upper()}_ROOT",
                "fallback_dir_name": resolved_root,
            }
        try:
            save_custom_subject_profile(
                {
                    "key": profile_key,
                    "catalog": {
                        "title": title,
                        "subject_label": clean_label,
                        "status": "已启用",
                        "stage": "自定义",
                        "summary": f"{clean_label}的资料识别、人工确认与私有知识库工作流。",
                        "capabilities": ["资料导入", "知识点确认", "原文引用"],
                        "source_strategy": "统一资料路由 + 结构化知识点确认",
                        "notes": "由页面向导创建，可继续通过配置文件调整抽取重点。",
                        "enabled": True,
                    },
                    "local_source": local_source,
                    "max_points": 12,
                    "extraction_guidance": extraction_guidance.strip(),
                }
            )
        except (OSError, ValueError, RuntimeError) as exc:
            st.error(f"创建专业课失败：{exc}")
            return

        st.session_state["_pending_kb_subject"] = clean_label
        _queue_toast(f"已创建“{clean_label}”，现在可以导入资料")
        st.rerun()


def _update_knowledge_mastery(knowledge_id, mastery_state):
    if not knowledge_id:
        return
    conn = sqlite3.connect(MEMORY_DB)
    try:
        ensure_knowledge_schema(conn)
        conn.execute("UPDATE user_knowledge SET mastery_state=?, updated_at=datetime('now') WHERE id=?", (mastery_state, knowledge_id))
        conn.commit()
    finally:
        conn.close()


def render_knowledge_page():
    """渲染专业课知识点识别系统：资料识别、确认入库、复习发散。"""
    user_id = st.session_state.get("user_id", 1)
    _ensure_session_draft_state()
    _ensure_persist_state()
    _show_pending_toast()

    st.markdown(
        """
        <div class="main-title">
            <h1>专业课知识点识别系统</h1>
            <p>围绕专业课资料做“来源优先”的私有知识库：先识别和清洗资料，再确认知识点，最后回到原文依据做复习与检索。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("已配置的专业课（管理与扩展）", expanded=False):
        _render_rag_knowledge_base_catalog()

    conn = sqlite3.connect(MEMORY_DB)
    try:
        c = conn.cursor()
        total_knowledge = c.execute("SELECT COUNT(*) FROM user_knowledge WHERE user_id=?", (user_id,)).fetchone()[0] or 0
        total_materials = _count_effective_materials(c, user_id)
        total_subjects = c.execute("SELECT COUNT(DISTINCT subject) FROM user_knowledge WHERE user_id=?", (user_id,)).fetchone()[0] or 0
    finally:
        conn.close()
    total_wrong_questions = count_user_wrong_questions(user_id)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("资料", total_materials)
    m2.metric("知识点", total_knowledge)
    m3.metric("错题", total_wrong_questions)
    m4.metric("学科", total_subjects)
    m5.metric("待确认", len(st.session_state.get("knowledge_drafts") or []))

    tab_input, tab_confirm, tab_repo, tab_wrong = st.tabs(
        ["1 导入并核对文本", "2 确认知识点", "3 我的知识库", "工具 · 错题本"]
    )
    subjects_kb = list_enabled_subjects()

    with tab_input:
        _render_stage_strip("1")
        _render_resume_material_panel(user_id)
        _render_subject_setup_wizard()
        pending_subject = st.session_state.pop("_pending_kb_subject", None)
        if pending_subject in subjects_kb:
            st.session_state["kb_subject_v2"] = pending_subject
        selected_subject = st.selectbox("学科", subjects_kb, key="kb_subject_v2")
        local_material_source = get_local_material_source_for_subject(selected_subject)
        local_tab_label = local_material_source.tab_label if local_material_source else "本地资料源"
        intro_left, intro_right = st.columns([1.4, 0.9])
        with intro_left:
            st.subheader("导入待识别资料")
            st.caption("先确认原始文本，再抽取候选知识点。所有来源最终都会走同一条清洗、抽取、确认、入库链路。")
            upload_tab, paste_tab, local_tab = st.tabs(["上传资料", "粘贴文本", local_tab_label])

            with upload_tab:
                with st.form("upload_material_v2"):
                    upload_chapter_name = st.text_input("章节 / 文件主题", placeholder="例如：数据结构 - 树与二叉树；多文件时将作为批次前缀")
                    uploaded_files = st.file_uploader(
                        "上传 PDF / 图片 / TXT（支持多文件）",
                        type=["pdf", "png", "jpg", "jpeg", "txt"],
                        key="material_upload_v2",
                        accept_multiple_files=True,
                    )
                    upload_submitted = st.form_submit_button("开始识别", use_container_width=True, type="primary")
                if upload_submitted:
                    if not uploaded_files:
                        st.warning("请上传 PDF / 图片 / TXT 文件。")
                    else:
                        _process_material_batch_uploads(
                            user_id=user_id,
                            subject=selected_subject,
                            chapter_name=upload_chapter_name,
                            uploaded_files=uploaded_files,
                        )

            with paste_tab:
                with st.form("paste_material_v2"):
                    pasted_chapter_name = st.text_input("章节 / 文件主题", placeholder="例如：操作系统 - 进程管理")
                    pasted_text = st.text_area("粘贴文本", height=200, placeholder="也可以直接粘贴讲义、笔记或真题解析文本")
                    paste_submitted = st.form_submit_button("确认文本并开始识别", use_container_width=True, type="primary")
                if paste_submitted:
                    if not pasted_chapter_name.strip():
                        st.warning("请填写章节或文件主题。")
                    elif not pasted_text.strip():
                        st.warning("请先粘贴要识别的文本。")
                    else:
                        _process_material_submission(
                            user_id=user_id,
                            subject=selected_subject,
                            chapter_name=pasted_chapter_name,
                            filename="pasted_text.txt",
                            pasted_text=pasted_text,
                        )

            with local_tab:
                if local_material_source is None:
                    st.info("当前学科暂未配置本地资料源。你仍然可以通过上传 PDF / 图片 / TXT 或粘贴文本使用专业课识别系统。")
                else:
                    local_root = get_local_material_root(local_material_source.key)
                    if local_root is None:
                        st.info(
                            f"未配置 {local_material_source.title} 目录。"
                            f" 可通过 {get_local_material_source_hint(local_material_source.key)} 提供资料。"
                        )
                        local_files = []
                    else:
                        local_files = list_local_material_files(local_material_source.key, limit=300)
                    if not local_files:
                        if local_root is not None:
                            st.info(f"已配置 {local_material_source.title} 目录，但当前没有读取到可导入的 PDF / 图片 / TXT / MD 文件。")
                    else:
                        local_query = st.text_input(
                            "搜索本地资料",
                            placeholder="按文件名或相对路径筛选",
                            key=f"local_material_search_{local_material_source.key}_v2",
                        )
                        filtered_files = [
                            item for item in local_files
                            if not local_query.strip()
                            or local_query.lower() in item["name"].lower()
                            or local_query.lower() in item["relative_path"].lower()
                        ]
                        st.caption(f"资料根目录：{local_root}")
                        if not filtered_files:
                            st.warning("没有匹配的本地资料文件。")
                        else:
                            local_file_map = {item["relative_path"]: item for item in filtered_files}
                            selected_relative_path = st.selectbox(
                                "选择本地资料",
                                options=list(local_file_map.keys()),
                                format_func=lambda key: _format_local_material_option(local_file_map[key]),
                                key=f"local_material_selected_{local_material_source.key}_v2",
                            )
                            local_chapter_name = st.text_input(
                                "章节 / 文件主题",
                                value=_guess_chapter_name_from_relative_path(selected_relative_path),
                                key=f"local_material_chapter_{local_material_source.key}_v2",
                            )
                            if st.button(
                                "导入并识别",
                                use_container_width=True,
                                type="primary",
                                key=f"import_local_material_{local_material_source.key}_v2",
                            ):
                                if not local_chapter_name.strip():
                                    st.warning("请填写章节或文件主题。")
                                else:
                                    try:
                                        filename, file_bytes = read_local_material(local_material_source.key, selected_relative_path)
                                        _process_material_submission(
                                            user_id=user_id,
                                            subject=selected_subject,
                                            chapter_name=local_chapter_name,
                                            filename=filename,
                                            file_bytes=file_bytes,
                                        )
                                    except Exception as exc:
                                        st.error(f"导入 {local_material_source.title} 失败：{exc}")

        with intro_right:
            _render_info_card(
                "当前导入策略",
                "文字型 PDF 先走 PyMuPDF 直提，质量不足时自动尝试 OCR 回退；图片走 OCR，TXT / MD / 粘贴文本直接清洗后进入人工确认。",
                metrics=[
                    ("默认学科", selected_subject),
                    ("OCR 引擎", "RapidOCR + PaddleOCR"),
                    ("PDF 文字提取", "PyMuPDF"),
                    ("引用锚点", "页码 / 题号"),
                ],
                badges=[
                    ("NotebookLM 风格来源优先", "good"),
                    ("支持后续小众专业课扩展", ""),
                ],
                kicker="流程说明",
            )
            _render_material_library_snapshot(user_id, selected_subject)

        if st.session_state.get("_ocr_preview") is not None:
            ocr_text = st.session_state._ocr_preview
            material_result = st.session_state.get("_material_result", {})
            raw_text = material_result.get("raw_extracted_text") or ocr_text
            report = material_result.get("clean_report") or {}
            st.markdown("---")
            compare_left, compare_right = st.columns([1.45, 0.95])
            with compare_left:
                st.subheader("识别与清洗对比")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("原始字符", len(raw_text))
                m2.metric("清洗后字符", len(ocr_text))
                m3.metric("处理方式", material_result.get("process_method", "unknown"))
                m4.metric("清理比例", f"{report.get('removal_ratio', 0.0) * 100:.1f}%")

                raw_col, clean_col = st.columns(2)
                with raw_col:
                    st.text_area("清洗前 / 原始提取", value=raw_text, height=330, key="ocr_raw_area_v2", disabled=True)
                with clean_col:
                    edited_text = st.text_area("清洗后 / 可继续修正", value=ocr_text, height=330, key="ocr_edit_area_v2")

                c1, c2, c3 = st.columns([2.2, 1.25, 1])
                with c1:
                    if st.button("文本已核对，生成候选知识点", use_container_width=True, type="primary"):
                        if not edited_text.strip():
                            st.warning("识别文本为空。")
                        else:
                            if not _persist_active_confirmed_text(edited_text, status="text_confirmed"):
                                st.stop()
                            active_subject = st.session_state.get("_ocr_subject", "")
                            subject_profile = get_rag_knowledge_base_by_subject(active_subject)
                            drafts, draft_warnings = _extract_drafts_with_progress(
                                text=edited_text,
                                subject=active_subject,
                                chapter_name=st.session_state.get("_ocr_chapter", ""),
                                max_points=subject_profile.max_points if subject_profile else 12,
                                extraction_guidance=(
                                    subject_profile.extraction_guidance if subject_profile else ""
                                ),
                            )
                            _set_draft_session_data([knowledge_point_to_dict(point) for point in drafts], draft_warnings)
                            _persist_active_workflow_snapshot(status="drafted")
                            _update_current_task(
                                "drafted",
                                note=f"已生成 {len(drafts)} 条候选知识点",
                                warning_count=len(draft_warnings or []),
                            )
                            _queue_toast(f"已生成 {len(drafts)} 条候选知识点")
                            st.rerun()
                with c2:
                    if st.button("保存文本，稍后继续", use_container_width=True):
                        if not edited_text.strip():
                            st.warning("识别文本为空。")
                        else:
                            if not _persist_active_confirmed_text(edited_text, status="text_confirmed"):
                                st.stop()
                            st.session_state["_ocr_preview"] = edited_text
                            st.session_state["_material_result"]["extracted_text"] = edited_text
                            _queue_toast("已保存当前文本，可稍后从未完成资料继续")
                            st.rerun()
                with c3:
                    if st.button("重新上传", use_container_width=True):
                        _clear_active_material_state(discard_unsaved=True)
                        _clear_current_draft_session()
                        st.rerun()

            with compare_right:
                _render_material_report(material_result)
                _render_material_library_snapshot(user_id, st.session_state.get("_ocr_subject", selected_subject))

    with tab_confirm:
        _render_stage_strip("2")
        st.subheader("候选知识点确认")
        draft_points = st.session_state.get("knowledge_drafts") or []
        draft_warnings = st.session_state.get("knowledge_draft_warnings") or []
        if draft_points:
            selected_draft_id = _ensure_selected_draft(draft_points)
            point_map = {point.get("_draft_id"): point for point in draft_points}
            queue_col, editor_col = st.columns([0.95, 1.45])
            with queue_col:
                _render_info_card(
                    "候选草稿队列",
                    "先在左侧切换知识点，再在右侧编辑。只有确认后的知识点才会进入待保存区。",
                    metrics=[
                        ("候选草稿", len(draft_points)),
                        ("已确认", len(st.session_state.get("confirmed_knowledge_drafts") or [])),
                        ("已删除", st.session_state.get("deleted_knowledge_draft_count", 0)),
                        ("草稿警告", len(draft_warnings)),
                    ],
                    badges=[
                        (st.session_state.get("_ocr_subject", "未选择学科"), ""),
                        (st.session_state.get("_ocr_chapter", "未填写章节"), ""),
                    ],
                    kicker="确认工作台",
                )
                if draft_warnings:
                    for warning in draft_warnings:
                        st.warning(warning)
                st.radio(
                    "候选知识点",
                    options=list(point_map.keys()),
                    index=list(point_map.keys()).index(selected_draft_id),
                    format_func=lambda draft_id: _format_draft_option(point_map[draft_id]),
                    key="selected_draft_id",
                    label_visibility="collapsed",
                )
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("确认全部", use_container_width=True):
                        _confirm_all_drafts_in_session()
                        _persist_active_workflow_snapshot(status="drafted")
                        st.rerun()
                with b2:
                    if st.button("清空本次草稿", use_container_width=True):
                        _clear_current_draft_session()
                        _persist_active_workflow_snapshot(status="text_confirmed")
                        st.rerun()
            with editor_col:
                selected_point = point_map.get(st.session_state.get("selected_draft_id"))
                if selected_point:
                    selected_index = draft_points.index(selected_point) + 1
                    _render_draft_editor(selected_point, selected_index)
        else:
            st.markdown(
                """
                <div class="pk-empty-state">
                    暂无候选草稿。请先回到“识别资料”抽取知识点，系统会把每条知识点和原文证据一起带过来。
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.subheader("已确认，待保存")
        _render_confirmed_panel(
            user_id,
            st.session_state.get("_ocr_subject", ""),
            st.session_state.get("_ocr_chapter", ""),
            st.session_state.get("_ocr_material_id"),
            st.session_state.get("_material_result", {}),
        )

    with tab_repo:
        _render_stage_strip("3")
        st.markdown(
            """
            <div class="pk-section-heading">
                <h2>我的知识库与复习</h2>
                <p>检索已入库知识点，查看原文依据，维护掌握状态，并为后续 RAG 和关系图保留稳定的数据入口。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _render_private_repository(user_id)

    with tab_wrong:
        _render_stage_strip("3")
        st.markdown(
            """
            <div class="pk-section-heading">
                <h2>错题上传与复习</h2>
                <p>批量上传错题截图，OCR 后先生成草稿，再统一加入错题本，后续可像背单词一样持续复习。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_wrong_question_workspace(
            user_id,
            subjects_kb,
            image_ocr_fn=extract_text_from_image,
            pdf_ocr_fn=lambda path: extract_text_from_pdf_paddleocr(path),
            pdf_ocr_available=is_rapid_ocr_available() or is_paddle_ocr_available(),
        )
