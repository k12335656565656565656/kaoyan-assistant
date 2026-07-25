"""专业知识库独立调试入口。

生产环境应从 ``app.py`` 的登录流程进入。只有显式配置
``KAOYAN_STANDALONE_USER_ID`` 时，才允许直接运行此文件。
"""
import os

import streamlit as st
from knowledge_base import ensure_db, render_knowledge_page
from professional_knowledge.ui import inject_professional_knowledge_styles

# 页面配置
st.set_page_config(page_title="专业知识库", page_icon="📚", layout="wide")

# 与主应用共用同一套专业课工作台视觉规范。
inject_professional_knowledge_styles()

# 初始化数据库
ensure_db()

# 独立入口没有登录流程，必须由启动者明确指定隔离后的测试用户。
standalone_user_id = os.environ.get("KAOYAN_STANDALONE_USER_ID", "").strip()
if not standalone_user_id.isdigit() or int(standalone_user_id) <= 0:
    st.error("独立调试入口未配置用户身份。请从主应用登录后进入专业课。")
    st.stop()
st.session_state["user_id"] = int(standalone_user_id)

render_knowledge_page()
