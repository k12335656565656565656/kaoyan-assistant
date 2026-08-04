import streamlit as st
from datetime import datetime, timedelta
from report_generator import generate_pdf_report
import os


def show():
    st.title("📄 运营报告生成")

    st.markdown("### 生成运营分析报告")

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        report_start = st.date_input("报告开始日期", value=datetime.now() - timedelta(days=30), key="r_start")
    with col_r2:
        report_end = st.date_input("报告结束日期", value=datetime.now(), key="r_end")

    report_type = st.selectbox("报告类型", ["月报", "周报", "日报", "自定义"])

    if st.button("📄 生成 PDF 报告", type="primary", use_container_width=True):
        with st.spinner("正在生成专业报告..."):
            pdf_path = generate_pdf_report(
                str(report_start),
                str(report_end),
                report_type
            )

            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()

                st.success("✅ 报告生成完成！")
                st.download_button(
                    "📥 下载 PDF 报告",
                    pdf_bytes,
                    f"考研RAG运营报告_{report_start}_{report_end}.pdf",
                    "application/pdf",
                    use_container_width=True
                )
            else:
                st.error("报告生成失败，请检查数据")