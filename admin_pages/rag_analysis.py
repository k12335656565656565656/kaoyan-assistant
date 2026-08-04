import streamlit as st
from utils.database import query_db, get_single_value


def show():
    import plotly.express as px

    st.title("🤖 RAG 系统效果分析")

    try:
        check = query_db("SELECT name FROM sqlite_master WHERE name='rag_record'")
        if not check:
            st.warning("⚠️ rag_record 表尚未创建，请先运行 migrate_db.py")
            return

        total_rag = get_single_value("SELECT COUNT(*) FROM rag_record")
        avg_similarity = get_single_value("SELECT AVG(top_similarity) FROM rag_record WHERE top_similarity > 0")
        avg_response = get_single_value("SELECT AVG(response_time_ms) FROM rag_record WHERE response_time_ms > 0")

        if total_rag > 0:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📝 记录问答数", f"{total_rag:,}")
            with col2:
                st.metric("📊 平均召回相似度", f"{avg_similarity:.3f}" if avg_similarity else "N/A")
            with col3:
                st.metric("⏱️ 平均响应时间", f"{avg_response:.0f}ms" if avg_response else "N/A")

            st.markdown("---")

            st.subheader("召回相似度分布")
            df_sim = query_db("""
                              SELECT CASE
                                         WHEN top_similarity >= 0.9 THEN '优秀(≥0.9)'
                                         WHEN top_similarity >= 0.7 THEN '良好(0.7-0.9)'
                                         WHEN top_similarity >= 0.5 THEN '一般(0.5-0.7)'
                                         ELSE '较差(<0.5)'
                                         END  as 质量等级,
                                     COUNT(*) as 数量
                              FROM rag_record
                              WHERE top_similarity > 0
                              GROUP BY 质量等级
                              ORDER BY top_similarity DESC
                              """, as_df=True)

            if not df_sim.empty:
                fig = px.pie(df_sim, names='质量等级', values='数量', hole=0.3)
                st.plotly_chart(fig, use_container_width=True)

            st.subheader("最近 RAG 记录")
            df_recent = query_db("""
                                 SELECT qa.question_text   as 问题,
                                        r.top_similarity   as 最高相似度,
                                        r.response_time_ms as 响应时间ms,
                                        r.token_used       as Token消耗,
                                        r.created_at       as 时间
                                 FROM rag_record r
                                          LEFT JOIN question_analysis qa ON r.question_id = qa.id
                                 ORDER BY r.created_at DESC LIMIT 20
                                 """, as_df=True)
            st.dataframe(df_recent, use_container_width=True, hide_index=True)
        else:
            st.info("暂无 RAG 记录数据")

    except Exception as e:
        st.error(f"加载 RAG 数据失败: {e}")
