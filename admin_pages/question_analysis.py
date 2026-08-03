import streamlit as st
from datetime import datetime, timedelta
from utils.database import query_db


def _difficulty_text(diff):
    if diff and '★★★' in diff:
        return '困难'
    elif diff and '★★☆' in diff:
        return '中等'
    elif diff and '★☆☆' in diff:
        return '简单'
    return diff or '未分类'


def show():
    st.title("🔥 问题分析中心")

    search_query = st.text_input("🔍 搜索问题", placeholder="输入关键词搜索...")

    if search_query:
        st.subheader(f"搜索结果：{search_query}")
        df_search = query_db("""
                             SELECT timestamp as 时间, username as 用户, detail as 问题内容
                             FROM visit_log
                             WHERE action ='提问' AND detail LIKE ?
                             ORDER BY id DESC LIMIT 50
                             """, (f"%{search_query}%",), as_df=True)

        if not df_search.empty:
            st.dataframe(df_search, use_container_width=True, hide_index=True)
        else:
            st.info("未找到相关问题")
        st.markdown("---")

    st.subheader("📊 高频问题排行榜")

    days = st.slider("统计最近天数", 1, 90, 30)
    date_limit = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    df_questions = query_db("""
                            SELECT detail as 问题内容, COUNT(*) as 出现次数
                            FROM visit_log
                            WHERE action ='提问' AND detail != '' AND timestamp >= ?
                            GROUP BY detail
                            ORDER BY 出现次数 DESC
                                LIMIT 30
                            """, (date_limit,), as_df=True)

    if not df_questions.empty:
        st.dataframe(df_questions, use_container_width=True, hide_index=True)

        csv = df_questions.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 导出高频问题 CSV",
            csv,
            f"高频问题_{date_limit}_{datetime.now().strftime('%Y%m%d')}.csv",
            "text/csv"
        )
    else:
        st.info("暂无数据")

    st.markdown("---")

    st.subheader("📚 已分类问题库")
    try:
        df_classified = query_db("""
                                 SELECT qa.subject         as 科目,
                                        qa.chapter         as 章节,
                                        qa.knowledge_point as 知识点,
                                        qa.difficulty      as 难度,
                                        qa.question_text   as 问题,
                                        qa.created_at      as 分类时间
                                 FROM question_analysis qa
                                 WHERE qa.subject != ''
                                 ORDER BY qa.created_at DESC LIMIT 50
                                 """, as_df=True)

        if not df_classified.empty:
            df_classified['难度'] = df_classified['难度'].apply(_difficulty_text)
            st.dataframe(df_classified, use_container_width=True, hide_index=True)

            subjects = df_classified['科目'].unique().tolist()
            selected_subject = st.selectbox("按科目筛选", ["全部"] + subjects)

            if selected_subject != "全部":
                filtered = df_classified[df_classified['科目'] == selected_subject]
                st.dataframe(filtered, use_container_width=True, hide_index=True)
        else:
            st.info("暂无分类数据。请确保已配置自动分类功能。")
    except Exception as e:
        st.warning(f"分类表不可用: {e}")