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


# ==================== UI 渲染 ====================

def render_knowledge_page():
    """渲染专业知识库页面（4 个 Tab）"""
    user_id = st.session_state.get("user_id", 1)

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
- 图片会直接用 AI 多模态识别，无需 OCR
""")

        # 上传表单
        with st.form("upload_material"):
            chapter_name = st.text_input("章节名称", placeholder="例如：第一章 栈和队列")
            uploaded_file = st.file_uploader("上传资料", type=["pdf", "png", "jpg", "jpeg", "txt"], key="material_upload")
            if st.form_submit_button("上传并处理", use_container_width=True):
                if uploaded_file and chapter_name.strip():
                    # 保存文件
                    user_dir = Path(f"data/user_materials/{user_id}")
                    user_dir.mkdir(parents=True, exist_ok=True)
                    file_path = user_dir / uploaded_file.name
                    file_path.write_bytes(uploaded_file.getvalue())

                    # 记录到数据库
                    file_type = uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else "unknown"
                    conn = sqlite3.connect(MEMORY_DB)
                    c = conn.cursor()
                    c.execute("""INSERT INTO user_materials
                        (user_id, subject, filename, chapter_name, file_path, file_type, processing_status)
                        VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
                        (user_id, selected_subject, uploaded_file.name, chapter_name.strip(), str(file_path), file_type))
                    material_id = c.lastrowid
                    conn.commit()
                    conn.close()

                    # OCR 识别
                    content = ""
                    if file_type == "txt":
                        content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
                    elif file_type == "pdf":
                        if check_umiocr_available():
                            with st.spinner("正在用 umi-ocr 识别 PDF..."):
                                content = extract_text_from_pdf_umiocr(file_path)
                        else:
                            with st.spinner("正在解析 PDF..."):
                                content = extract_text_from_pdf(file_path)
                    elif file_type in ("png", "jpg", "jpeg"):
                        with st.spinner("正在识别图片..."):
                            content = extract_text_from_image(uploaded_file.getvalue())

                    st.session_state._ocr_preview = content
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

            st.markdown("---")
            st.subheader("📝 识别结果预览")

            st.caption(f"识别文字：{len(ocr_text)} 字 | 章节：{chapter_name}")

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
                            conn = sqlite3.connect(MEMORY_DB)
                            c = conn.cursor()
                            try:
                                llm_result = extract_knowledge_from_text(edited_text, selected_subject, chapter_name)
                                count = save_knowledge_points(user_id, material_id, selected_subject, chapter_name, llm_result)
                                conn.commit()
                                conn.close()
                                del st.session_state._ocr_preview
                                del st.session_state._ocr_material_id
                                del st.session_state._ocr_chapter
                                del st.session_state._ocr_subject
                                del st.session_state._ocr_file_type
                                st.success(f"✅ 上传成功！提取了 {count} 个知识点。")
                                st.rerun()
                            except Exception as e:
                                conn.close()
                                st.warning(f"AI 处理失败，文件已保存: {e}")
                    else:
                        st.warning("识别结果为空，无法归纳")
            with col_retry:
                if st.button("🔄 重新上传", use_container_width=True):
                    del st.session_state._ocr_preview
                    del st.session_state._ocr_material_id
                    del st.session_state._ocr_chapter
                    del st.session_state._ocr_subject
                    del st.session_state._ocr_file_type
                    st.rerun()

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
