import streamlit as st
from utils.database import query_db


def show():
    st.title("👤 用户行为分析")

    st.subheader("🏅 活跃用户排行榜")
    df_users = query_db("""
                        SELECT username,
                               COUNT(*)                                       as total_ops,
                               SUM(CASE WHEN action='提问' THEN 1 ELSE 0 END) as questions,
                               SUM(CASE WHEN action='登录' THEN 1 ELSE 0 END) as logins,
                               MIN(timestamp)                                 as first_seen,
                               MAX(timestamp)                                 as last_seen
                        FROM visit_log
                        GROUP BY username
                        ORDER BY questions DESC LIMIT 20
                        """, as_df=True)

    if not df_users.empty:
        st.dataframe(df_users, use_container_width=True, hide_index=True)

        selected_user = st.selectbox("选择用户查看画像", df_users['username'].tolist())

        if selected_user:
            st.markdown("---")
            st.subheader(f"👤 用户画像：{selected_user}")

            user_data = df_users[df_users['username'] == selected_user].iloc[0]

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("累计提问", user_data['questions'])
            with col_b:
                st.metric("首次访问", str(user_data['first_seen'])[:10])
            with col_c:
                st.metric("最近访问", str(user_data['last_seen'])[:10])

            st.markdown("**近期提问：**")
            user_questions = query_db("""
                                      SELECT timestamp, detail
                                      FROM visit_log
                                      WHERE username=? AND action ='提问'
                                      ORDER BY id DESC LIMIT 10
                                      """, (selected_user,))
            for t, q in user_questions:
                st.markdown(f"- `{t[:19]}` {q[:80]}")

            try:
                user_subjects = query_db("""
                                         SELECT qa.subject, COUNT(*) as cnt
                                         FROM question_analysis qa
                                                  JOIN visit_log vl ON qa.visit_log_id = vl.id
                                         WHERE vl.username = ?
                                         GROUP BY qa.subject
                                         ORDER BY cnt DESC
                                         """, (selected_user,))
                if user_subjects:
                    st.markdown("**科目偏好：**")
                    for subj, cnt in user_subjects:
                        st.progress(cnt / sum(c for _, c in user_subjects), text=f"{subj}: {cnt}次")
            except:
                pass
    else:
        st.info("暂无用户数据")