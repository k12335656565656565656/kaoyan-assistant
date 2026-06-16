"""
专业知识库模块 — 独立包
功能：上传资料 · OCR识别 · 错题本 · 复习本 · AI出题
"""

import streamlit as st
import sqlite3
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
import json
import base64
import urllib.request
import urllib.error
import re
from pathlib import Path
from uuid import uuid4

from schemas.knowledge_schema import (
    knowledge_point_to_dict,
    normalize_knowledge_point_draft,
    validate_required_fields,
)
from services.knowledge_json_extractor import extract_knowledge_points_as_drafts
from services.material_router import route_material_input

# ==================== 配置（从环境变量读取） ====================
MEMORY_DB = os.environ.get("MEMORY_DB", "data/memory.db")
API_KEY = os.environ.get("AI_API_KEY", "")
API_BASE = os.environ.get("AI_API_BASE", "https://api.xiaomimimo.com/v1")
UMI_OCR_URL = os.environ.get("UMI_OCR_URL", "http://localhost:1224")


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


def ensure_db():
    """自动创建数据库和表（独立运行时调用）"""
    os.makedirs(os.path.dirname(MEMORY_DB) or "data", exist_ok=True)
    conn = sqlite3.connect(MEMORY_DB)
    init_knowledge_db(conn)
    conn.commit()
    conn.close()


# ==================== LLM 辅助 ====================

def _call_llm_api(prompt, model="mimo-v2.5", max_tokens=1500):
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3
    }
    req = urllib.request.Request(
        API_BASE + "/chat/completions",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]


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
    return "\n\n".join(all_text)[:8000]


def extract_text_from_image(file_bytes):
    """用 glm-4v-flash 识别图片中的文字"""
    img_b64 = base64.b64encode(file_bytes).decode()
    data = {
        "model": "mimo-v2.5",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "请识别这张图片中的所有文字内容，只输出文字，不要添加任何说明。"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
        ]}],
        "max_tokens": 2000,
        "temperature": 0
    }
    req = urllib.request.Request(
        API_BASE + "/chat/completions",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]


def extract_knowledge_from_pdf_images(file_path, subject, chapter_name):
    """将 PDF 每页转为图片，用多模态 AI 直接提取知识点"""
    import fitz
    doc = fitz.open(str(file_path))
    all_knowledge = []

    for page_num in range(min(len(doc), 20)):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("jpeg")
        img_b64 = base64.b64encode(img_bytes).decode()

        prompt = f"""请从这张图片中提取所有知识点。

学科：{subject}
章节：{chapter_name}
这是 PDF 第 {page_num+1} 页。

输出格式（严格遵守）：
知识点1: [知识点名称] - [1-2句话简要说明核心概念]
知识点2: [知识点名称] - [1-2句话简要说明核心概念]
...

要求：
- 提取所有可见的知识点
- 如果是公式或定理，写出名称和简要含义
- 如果没有知识点，输出「无」"""

        data = {
            "model": "mimo-v2.5",
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
            ]}],
            "max_tokens": 1500,
            "temperature": 0
        }
        req = urllib.request.Request(
            API_BASE + "/chat/completions",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]
            if "无" not in result[:10]:
                all_knowledge.append(result)
        except:
            pass

    doc.close()
    return "\n".join(all_knowledge)


def extract_knowledge_from_image(file_bytes, subject, chapter_name):
    """用多模态 AI 直接从图片提取知识点"""
    img_b64 = base64.b64encode(file_bytes).decode()
    prompt = f"""请仔细观察这张图片，从中提取所有知识点。

学科：{subject}
章节：{chapter_name}

输出格式（严格遵守）：
知识点1: [知识点名称] - [1-2句话简要说明核心概念]
知识点2: [知识点名称] - [1-2句话简要说明核心概念]
...

要求：
- 提取所有可见的知识点
- 知识点名称用中文
- 简要说明要准确、简洁
- 如果是公式或定理，写出名称和简要含义"""

    data = {
        "model": "mimo-v2.5",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
        ]}],
        "max_tokens": 2000,
        "temperature": 0
    }
    req = urllib.request.Request(
        API_BASE + "/chat/completions",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]


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
    confirmed.extend(drafts)
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
    st.session_state["_draft_knowledge_points"] = []
    st.session_state["_draft_knowledge_warnings"] = []


# ==================== UI 渲染 ====================

def render_knowledge_page():
    """渲染专业知识库页面（4 个 Tab）"""
    user_id = st.session_state.get("user_id", 1)
    _ensure_session_draft_state()

    if not API_KEY:
        st.error("⚠️ 未设置 API Key。请设置环境变量 `AI_API_KEY` 后重启。")
        st.code("export AI_API_KEY='sk-xxx'  # Linux/Mac\nset AI_API_KEY=sk-xxx  # Windows", language="bash")
        st.stop()

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
- 图片会直接用 AI 多模态识别，无需 OCR
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
                        with st.spinner("正在归纳知识点..."):
                            try:
                                drafts, draft_warnings = extract_knowledge_points_as_drafts(
                                    edited_text,
                                    subject=selected_subject,
                                    chapter_name=chapter_name,
                                    max_points=12,
                                    llm_callable=lambda prompt: _call_llm_api(prompt, model="mimo-v2.5", max_tokens=2200),
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
                    if "_material_result" in st.session_state:
                        del st.session_state._material_result
                    _clear_current_draft_session()
                    st.rerun()

            draft_points = st.session_state.get("knowledge_drafts") or []
            draft_warnings = st.session_state.get("knowledge_draft_warnings") or []
            confirmed_drafts = st.session_state.get("confirmed_knowledge_drafts") or []
            deleted_count = st.session_state.get("deleted_knowledge_draft_count", 0)
            if draft_points:
                st.markdown("---")
                st.subheader("🧩 候选知识点草稿确认区")
                st.info("当前阶段仅完成候选知识点确认流程。已确认草稿暂存在当前会话中，尚未正式写入私有知识库。正式入库将在 PR6 实现。")
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
                st.info("当前阶段仅完成候选知识点确认流程。已确认草稿暂存在当前会话中，尚未正式写入私有知识库。正式入库将在 PR6 实现。")
                for warning in draft_warnings:
                    st.warning(warning)

            if confirmed_drafts:
                st.markdown("---")
                st.subheader("✅ 本次已确认知识点")
                for idx, point in enumerate(confirmed_drafts, start=1):
                    title = point.get("knowledge_name") or f"已确认知识点 {idx}"
                    ktype = point.get("knowledge_type") or "未标注类型"
                    with st.expander(f"{idx}. {title} | {ktype}"):
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
