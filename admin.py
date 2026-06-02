"""考研RAG 管理后台 — http://localhost:8502"""
import streamlit as st
import sqlite3, hashlib, os
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="考研RAG 管理后台", page_icon="🔐", layout="wide")

ADMIN_PASS_FILE = Path.home() / ".kaoyan_admin_pass"
MEMORY_DB = "data/memory.db"

def _ensure_admin_pass():
    """启动时即生成密码文件，不等到登录"""
    if not ADMIN_PASS_FILE.exists():
        import secrets
        pw = secrets.token_hex(4)
        ADMIN_PASS_FILE.write_text(pw)
        return pw
    return ADMIN_PASS_FILE.read_text().strip()

_ADMIN_PW = _ensure_admin_pass()

def get_admin_pass():
    return _ADMIN_PW

def check_admin_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest() == hashlib.sha256(get_admin_pass().encode()).hexdigest()

# ─── 登录 ───
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

if not st.session_state.admin_logged_in:
    st.title("🔐 管理后台")
    with st.form("admin_login"):
        pwd = st.text_input("管理密码", type="password")
        if st.form_submit_button("登录", use_container_width=True, type="primary"):
            if check_admin_password(pwd):
                st.session_state.admin_logged_in = True
                st.rerun()
            else:
                st.error("密码错误")
    st.stop()

# ─── 主界面 ───
st.title("📊 考研RAG 管理后台")
st.caption(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

if st.button("🚪 退出", key="logout"):
    st.session_state.admin_logged_in = False
    st.rerun()

st.markdown("---")

def query_db(sql, params=()):
    conn = sqlite3.connect(MEMORY_DB)
    c = conn.cursor()
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return rows

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📜 实时日志", "👤 用户统计", "❓ 热门问题", "📅 按日期查询", "💬 用户建议"])

with tab1:
    st.subheader("最近 100 条访问记录")
    auto = st.checkbox("自动刷新 (10秒)", key="auto")
    if auto:
        st.rerun() if st.button("手动刷新") else __import__("time").sleep(0)
    else:
        st.button("🔄 手动刷新")
    rows = query_db("SELECT timestamp, username, action, detail FROM visit_log ORDER BY id DESC LIMIT 100")
    if rows:
        data = []
        for t, u, a, d in rows:
            t_short = t.split(".")[0] if "." in t else t
            data.append(f"| {t_short} | {u} | {a} | {d[:60]} |")
        header = "| 时间 | 用户 | 操作 | 详情 |\n|------|------|------|------|\n"
        st.markdown(header + "\n".join(data))
    else:
        st.info("暂无记录")

with tab2:
    st.subheader("用户活跃度")
    rows = query_db("""
        SELECT username, 
               COUNT(*) as total,
               SUM(CASE WHEN action='登录' THEN 1 ELSE 0 END) as logins,
               SUM(CASE WHEN action='提问' THEN 1 ELSE 0 END) as questions
        FROM visit_log GROUP BY username ORDER BY total DESC
    """)
    if rows:
        st.markdown("| 用户 | 总操作 | 登录 | 提问 |\n|------|--------|------|------|")
        for u, t, l, q in rows:
            st.markdown(f"| {u} | {t} | {l} | {q} |")
    else:
        st.info("暂无数据")

with tab3:
    st.subheader("热门提问 Top 10")
    rows = query_db("""
        SELECT detail, COUNT(*) as cnt FROM visit_log 
        WHERE action='提问' AND detail != '' 
        GROUP BY detail ORDER BY cnt DESC LIMIT 10
    """)
    if rows:
        for i, (q, c) in enumerate(rows, 1):
            st.markdown(f"{i}. **{q[:60]}** — {c} 次")
    else:
        st.info("暂无数据")

with tab4:
    st.subheader("按日期查询")
    date_str = st.date_input("选择日期", value=datetime.now()).strftime("%Y-%m-%d")
    rows = query_db("""
        SELECT timestamp, username, action, detail FROM visit_log
        WHERE timestamp LIKE ? ORDER BY id DESC
    """, (f"{date_str}%",))
    st.caption(f"{date_str} 共 {len(rows)} 条记录")
    for t, u, a, d in rows:
        st.markdown(f"`{t[:19]}` **{u}** _{a}_ → {d[:50]}")

with tab5:
    st.subheader("用户建议")
    rows = query_db("""
        SELECT id, username, content, created_at FROM suggestions ORDER BY id DESC LIMIT 50
    """)
    if rows:
        for sid, u, c, t in rows:
            st.markdown(f"**{u}** `{t[:19]}`")
            st.markdown(f"> {c}")
            st.markdown("---")
    else:
        st.info("暂无建议")
