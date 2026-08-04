import streamlit as st
from datetime import datetime, timedelta
from utils.database import query_db, get_single_value


def show():
    import plotly.express as px

    st.title("📊 数据总览 Dashboard")

    col_date1, col_date2 = st.columns(2)
    with col_date1:
        date_from = st.date_input("开始日期", value=datetime.now() - timedelta(days=30))
    with col_date2:
        date_to = st.date_input("结束日期", value=datetime.now())

    total_visits = get_single_value(
        "SELECT COUNT(*) FROM visit_log WHERE timestamp BETWEEN ? AND ?",
        (str(date_from), str(date_to) + " 23:59:59")
    )
    total_questions = get_single_value(
        "SELECT COUNT(*) FROM visit_log WHERE action='提问' AND timestamp BETWEEN ? AND ?",
        (str(date_from), str(date_to) + " 23:59:59")
    )
    unique_users = get_single_value(
        "SELECT COUNT(DISTINCT username) FROM visit_log WHERE timestamp BETWEEN ? AND ?",
        (str(date_from), str(date_to) + " 23:59:59")
    )

    try:
        total_answered = get_single_value("""
                                          SELECT COUNT(*)
                                          FROM question_analysis qa
                                                   JOIN visit_log vl ON qa.visit_log_id = vl.id
                                          WHERE qa.subject != '' AND vl.timestamp BETWEEN ? AND ?
                                          """, (str(date_from), str(date_to) + " 23:59:59"))
    except:
        total_answered = 0

    answer_rate = f"{(total_answered / total_questions * 100):.1f}%" if total_questions > 0 else "N/A"

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📈 访问总次数", f"{total_visits:,}")
    with col2:
        st.metric("❓ 提问总次数", f"{total_questions:,}")
    with col3:
        st.metric("👥 活跃用户数", f"{unique_users:,}")
    with col4:
        st.metric("✅ 问题分类率", answer_rate)

    st.markdown("---")

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("📈 每日提问趋势")
        df_trend = query_db("""
                            SELECT DATE (timestamp) as day, COUNT (*) as cnt
                            FROM visit_log
                            WHERE action ='提问' AND timestamp BETWEEN ? AND ?
                            GROUP BY day
                            ORDER BY day
                            """, (str(date_from), str(date_to) + " 23:59:59"), as_df=True)

        if not df_trend.empty:
            fig = px.line(df_trend, x='day', y='cnt', markers=True,
                          labels={'day': '日期', 'cnt': '提问数'})
            fig.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("暂无数据")

    with col_right:
        st.subheader("🔥 热门知识点分布")
        try:
            df_subjects = query_db("""
                                   SELECT subject, COUNT(*) as cnt
                                   FROM question_analysis
                                   WHERE subject != ''
                                   GROUP BY subject
                                   ORDER BY cnt DESC
                                   """, as_df=True)

            if not df_subjects.empty:
                fig = px.pie(df_subjects, names='subject', values='cnt', hole=0.4)
                fig.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("暂无分类数据")
        except:
            st.info("问题分类表暂无数据")

    st.markdown("---")

    st.subheader("🏆 热门提问 Top 10")
    top_questions = query_db("""
                             SELECT detail, COUNT(*) as cnt
                             FROM visit_log
                             WHERE action ='提问' AND detail != '' AND timestamp BETWEEN ? AND ?
                             GROUP BY detail
                             ORDER BY cnt DESC LIMIT 10
                             """, (str(date_from), str(date_to) + " 23:59:59"))

    if top_questions:
        for i, (q, c) in enumerate(top_questions, 1):
            st.markdown(f"**{i}.** {q[:80]} — `{c} 次`")
    else:
        st.info("暂无数据")
