import streamlit as st
import hashlib
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from admin_pages import dashboard, user_analysis, question_analysis, rag_analysis, report, gap_analysis

st.set_page_config(page_title="考研RAG 运营分析平台", page_icon="📊", layout="wide")

ADMIN_PASS_FILE = Path.home() / ".kaoyan_admin_pass"


def _ensure_admin_pass():
    env_password = os.getenv("ADMIN_PASSWORD")
    if env_password:
        return env_password
    if ADMIN_PASS_FILE.exists():
        return ADMIN_PASS_FILE.read_text(encoding='utf-8').strip()
    default_pw = "777888AA"
    ADMIN_PASS_FILE.write_text(default_pw, encoding='utf-8')
    return default_pw


_ADMIN_PW = _ensure_admin_pass()


def get_admin_pass():
    return _ADMIN_PW


def check_admin_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest() == hashlib.sha256(get_admin_pass().encode()).hexdigest()


if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

if not st.session_state.admin_logged_in:
    st.title("🔐 考研RAG 运营分析平台")
    with st.form("admin_login"):
        pwd = st.text_input("管理密码", type="password")
        if st.form_submit_button("登录", use_container_width=True, type="primary"):
            if check_admin_password(pwd):
                st.session_state.admin_logged_in = True
                st.rerun()
            else:
                st.error("密码错误")
    st.stop()

st.sidebar.title("📊 运营分析平台")
st.sidebar.caption(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

page = st.sidebar.radio(
    "导航",
    ["📊 数据总览", "👤 用户分析", "🔥 问题分析", "🤖 RAG效果", "🧩 缺口分析", "📄 报告中心", "⚙️ 系统管理"],
    index=0
)

if st.sidebar.button("🚪 退出登录", use_container_width=True):
    st.session_state.admin_logged_in = False
    st.rerun()

if page == "📊 数据总览":
    dashboard.show()
elif page == "👤 用户分析":
    user_analysis.show()
elif page == "🔥 问题分析":
    question_analysis.show()
elif page == "🤖 RAG效果":
    rag_analysis.show()
elif page == "🧩 缺口分析":
    gap_analysis.show()
elif page == "📄 报告中心":
    report.show()
elif page == "⚙️ 系统管理":
    st.title("⚙️ 系统管理")
    from utils.database import query_db

    st.subheader("📋 实时日志")
    rows = query_db("SELECT timestamp, username, action, detail FROM visit_log ORDER BY id DESC LIMIT 100")
    if rows:
        data = []
        for t, u, a, d in rows:
            t_short = t.split(".")[0] if "." in t else t
            data.append(f"| {t_short} | {u} | {a} | {d[:60]} |")
        header = "| 时间 | 用户 | 操作 | 详情 |\n|------|------|------|------|\n"
        st.markdown(header + "\n".join(data))

    st.markdown("---")
    st.subheader("💬 用户建议")
    suggestions = query_db("SELECT username, content, created_at FROM suggestions ORDER BY id DESC LIMIT 50")
    for u, c, t in suggestions:
        st.markdown(f"**{u}** `{t[:19]}`")
        st.markdown(f"> {c}")
        st.markdown("---")

    st.markdown("---")
    st.subheader("🔧 数据导出")
    col_e1, col_e2 = st.columns(2)
    with col_e1:
        if st.button("导出全部访问日志 CSV", use_container_width=True):
            df = query_db("SELECT * FROM visit_log ORDER BY id DESC", as_df=True)
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("下载", csv, "visit_log.csv", "text/csv")
    with col_e2:
        if st.button("导出用户建议 CSV", use_container_width=True):
            df = query_db("SELECT * FROM suggestions ORDER BY id DESC", as_df=True)
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("下载", csv, "suggestions.csv", "text/csv")