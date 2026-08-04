import streamlit as st
from utils.database import query_db

def show():
    st.title("🧩 知识库缺口分析")
    st.caption("统计高频提问中尚无知识库覆盖的问题，辅助内容团队补充资料")

    # 统计近30天提问中，question_analysis 里 subject 为空的（即未分类/未覆盖）
    df_gap = query_db("""
        SELECT vl.detail AS 问题内容, COUNT(*) AS 提问次数
        FROM visit_log vl
        LEFT JOIN question_analysis qa ON vl.id = qa.visit_log_id
        WHERE vl.action = '提问'
          AND vl.timestamp >= date('now', '-30 days')
          AND (qa.subject IS NULL OR qa.subject = '')
        GROUP BY vl.detail
        HAVING COUNT(*) >= 2
        ORDER BY 提问次数 DESC
        LIMIT 20
    """, as_df=True)

    if not df_gap.empty:
        st.warning(f"⚠️ 近30天发现 {len(df_gap)} 个知识库缺口，建议尽快补充相关内容")
        st.dataframe(df_gap, use_container_width=True, hide_index=True)

        # 生成补充建议
        st.subheader("📋 知识库补充建议")
        for idx, row in df_gap.iterrows():
            st.markdown(f"- **{row['问题内容'][:80]}** （提及{row['提问次数']}次）")
            st.markdown("  → 建议添加相关章节的知识文档，如该知识点的定义、例题和常见题型。")
    else:
        st.info("✅ 近30天未发现明显知识库缺口，系统覆盖良好")
