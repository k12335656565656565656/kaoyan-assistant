"""
专业知识库 — 独立运行入口
直接启动即可使用，无需登录。
"""
import streamlit as st
from professional_knowledge import render_professional_knowledge_system

# 页面配置
st.set_page_config(page_title="专业知识库", page_icon="📚", layout="wide")

render_professional_knowledge_system(standalone=True)
