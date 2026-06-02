"""
专业知识库 — 独立运行入口
直接启动即可使用，无需登录。
"""
import streamlit as st
from knowledge_base import ensure_db, render_knowledge_page

# 页面配置
st.set_page_config(page_title="专业知识库", page_icon="📚", layout="wide")

# CSS 样式
st.markdown("""
<style>
    .main-title { background: linear-gradient(135deg, #d77757 0%, #e8926a 100%); padding: 1.5rem; border-radius: 1rem; color: white; text-align: center; margin-bottom: 1rem; }
    .main-title h1 { font-size: 2rem; font-weight: 700; margin: 0; }
    .main-title p { opacity: 0.9; margin-top: 0.5rem; }
    .memory-card { padding: 12px; margin: 8px 0; background: #f8f9fa; border-radius: 10px; border-left: 4px solid #d77757; cursor: pointer; transition: all 0.3s; }
    .memory-card:hover { transform: translateX(5px); box-shadow: 0 4px 8px rgba(0,0,0,0.15); background: #fff; }
    .learning-card { padding: 8px; margin: 3px 0; background: #fff8f0; border-radius: 6px; border-left: 3px solid #e8926a; font-size: 12px; overflow: hidden; text-overflow: ellipsis; }
    .mastered-card { padding: 8px; margin: 3px 0; background: #f0faf4; border-radius: 6px; border-left: 3px solid #7cb896; font-size: 12px; overflow: hidden; text-overflow: ellipsis; }
    .qa-card { background: #fff; border-radius: 14px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(215,119,87,0.06); margin-bottom: 16px; }
    .ref-tag { display: inline-block; background: #fef5f0; color: #8b5a3c; padding: 3px 10px; border-radius: 20px; margin: 2px 4px; font-size: 12px; border: 1px solid #f0ddd0; }
    @media (max-width: 768px) {
        .main-title { padding: 1rem !important; }
        .main-title h1 { font-size: 1.3rem !important; }
        .main-title p { font-size: 0.85rem !important; }
        .qa-card { padding: 14px !important; font-size: 14px !important; }
        div[data-testid="stMetricValue"] { font-size: 1.1rem !important; }
        div[data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
    }
    @media (max-width: 480px) {
        .main-title { padding: 0.8rem !important; }
        .main-title h1 { font-size: 1.1rem !important; }
        .qa-card { padding: 10px !important; }
    }
</style>
""", unsafe_allow_html=True)

# 初始化数据库
ensure_db()

# 直接渲染知识库页面
render_knowledge_page()
