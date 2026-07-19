"""Standalone professional knowledge-base entrypoint with shared authentication."""

from datetime import datetime, timedelta
import sqlite3

import streamlit as st

try:
    import extra_streamlit_components as stx
except ModuleNotFoundError:  # Lightweight/dev environments can still use the login gate.
    class _SessionCookieManager:
        def get(self, key):
            return st.session_state.get("_fallback_cookies", {}).get(key)

        def set(self, key, value, **_kwargs):
            cookies = dict(st.session_state.get("_fallback_cookies", {}))
            cookies[key] = value
            st.session_state["_fallback_cookies"] = cookies

        def delete(self, key):
            cookies = dict(st.session_state.get("_fallback_cookies", {}))
            cookies.pop(key, None)
            st.session_state["_fallback_cookies"] = cookies

    class _FallbackComponents:
        CookieManager = _SessionCookieManager

    stx = _FallbackComponents()

from knowledge_base import MEMORY_DB, ensure_db, render_knowledge_page
from professional_knowledge.ui import inject_professional_knowledge_styles
from services.auth_service import (
    activate_authenticated_user,
    authenticate_user,
    clear_user_session_state,
    create_login_session,
    ensure_auth_schema,
    register_user,
    revoke_login_session,
    verify_login_session,
)


st.set_page_config(page_title="专业知识库", page_icon="📚", layout="wide")


def get_cookie_manager():
    """CookieManager must be session-local; caching it causes cross-user leakage."""
    if "cookie_manager" not in st.session_state:
        st.session_state.cookie_manager = stx.CookieManager()
    return st.session_state.cookie_manager


def ensure_auth_ready():
    ensure_db()
    with sqlite3.connect(MEMORY_DB) as conn:
        ensure_auth_schema(conn)


def logout(cookie_manager):
    revoke_login_session(MEMORY_DB, st.session_state.get("auth_token"))
    cookie_manager.delete("auth_token")
    clear_user_session_state(st.session_state, preserve_keys={"cookie_manager"})
    st.session_state.logged_in = False


def render_login_gate(cookie_manager) -> bool:
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        token = cookie_manager.get("auth_token")
        user_info = verify_login_session(MEMORY_DB, token)
        if user_info:
            activate_authenticated_user(
                st.session_state,
                user_info,
                token,
                preserve_keys={"cookie_manager"},
            )
            st.rerun()
        if token:
            cookie_manager.delete("auth_token")

    if st.session_state.logged_in:
        return True

    st.title("专业知识库")
    st.caption("请登录后访问你的专业课资料、知识点和错题。")
    login_tab, register_tab = st.tabs(["登录", "注册"])
    with login_tab:
        with st.form("kb_login_form"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录", type="primary", use_container_width=True)
        if submitted:
            user_info = authenticate_user(MEMORY_DB, username, password)
            if not user_info:
                st.error("用户名或密码错误")
            else:
                token = create_login_session(MEMORY_DB, user_info["user_id"])
                cookie_manager.set("auth_token", token, expires_at=datetime.now() + timedelta(days=30))
                activate_authenticated_user(
                    st.session_state,
                    user_info,
                    token,
                    preserve_keys={"cookie_manager"},
                )
                st.rerun()
    with register_tab:
        with st.form("kb_register_form"):
            username = st.text_input("新用户名")
            password = st.text_input("密码", type="password")
            password_confirm = st.text_input("确认密码", type="password")
            submitted = st.form_submit_button("注册", use_container_width=True)
        if submitted:
            if not username or not password:
                st.warning("请输入用户名和密码")
            elif password != password_confirm:
                st.error("两次密码不一致")
            elif len(password) < 3:
                st.error("密码至少 3 位")
            else:
                user_id = register_user(MEMORY_DB, username, password)
                if not user_id:
                    st.error("用户名已存在")
                else:
                    token = create_login_session(MEMORY_DB, user_id)
                    cookie_manager.set("auth_token", token, expires_at=datetime.now() + timedelta(days=30))
                    activate_authenticated_user(
                        st.session_state,
                        {"user_id": user_id, "username": username},
                        token,
                        preserve_keys={"cookie_manager"},
                    )
                    st.rerun()
    return False


ensure_auth_ready()
cookie_manager = get_cookie_manager()
if not render_login_gate(cookie_manager):
    st.stop()

with st.sidebar:
    st.caption(f"当前用户：{st.session_state['username']}")
    if st.button("退出登录", key="kb_logout", use_container_width=True):
        logout(cookie_manager)
        st.rerun()

inject_professional_knowledge_styles()
render_knowledge_page()
