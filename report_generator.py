import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import plotly.express as px
import plotly.io as pio
import pandas as pd
import sqlite3

FONT_PATHS = [
    "C:/Windows/Fonts/msyh.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/STKAITI.TTF",
]
CN_FONT = None
for fp in FONT_PATHS:
    if os.path.exists(fp):
        pdfmetrics.registerFont(TTFont('ChineseFont', fp))
        CN_FONT = 'ChineseFont'
        print(f"✅ 使用中文字体: {fp}")
        break

if CN_FONT is None:
    print("⚠️ 未找到中文字体，报告将无法显示中文")
    CN_FONT = 'Helvetica'

MEMORY_DB = os.path.join(os.path.dirname(__file__), "data", "memory.db")


def query_db(sql, params=()):
    conn = sqlite3.connect(MEMORY_DB)
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


def get_single_value(sql, params=()):
    conn = sqlite3.connect(MEMORY_DB)
    c = conn.cursor()
    c.execute(sql, params)
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0


def generate_chart_image(fig, filename):
    fig.update_layout(
        font=dict(family="Microsoft YaHei", size=14)
    )
    img_path = f"temp_{filename}.png"
    pio.write_image(fig, img_path, width=800, height=400)
    return img_path


def generate_pdf_report(start_date, end_date, report_type):
    report_dir = "reports"
    os.makedirs(report_dir, exist_ok=True)
    pdf_path = os.path.join(report_dir, f"运营报告_{start_date}_{end_date}.pdf")

    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                            topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    styles['Normal'].fontName = CN_FONT
    styles['Heading1'].fontName = CN_FONT
    styles['Heading2'].fontName = CN_FONT

    story = []
    temp_files = []

    story.append(Spacer(1, 1.5 * inch))
    cover_title = Paragraph("考研RAG智能问答系统运营分析报告", ParagraphStyle(
        'CoverTitle', fontName=CN_FONT, fontSize=28, alignment=TA_CENTER, spaceAfter=12))
    story.append(cover_title)
    story.append(Paragraph(f"报告周期：{start_date} 至 {end_date}",
                           ParagraphStyle('SubTitle', fontName=CN_FONT, fontSize=14, alignment=TA_CENTER,
                                          textColor=colors.grey)))
    story.append(Paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
                           ParagraphStyle('SubTitle', fontName=CN_FONT, fontSize=14, alignment=TA_CENTER,
                                          textColor=colors.grey)))
    story.append(Spacer(1, 1.5 * inch))

    date_filter_start = start_date
    date_filter_end = end_date + " 23:59:59"

    total_visits = get_single_value(
        "SELECT COUNT(*) FROM visit_log WHERE timestamp BETWEEN ? AND ?",
        (date_filter_start, date_filter_end))
    total_questions = get_single_value(
        "SELECT COUNT(*) FROM visit_log WHERE action='提问' AND timestamp BETWEEN ? AND ?",
        (date_filter_start, date_filter_end))
    unique_users = get_single_value(
        "SELECT COUNT(DISTINCT username) FROM visit_log WHERE timestamp BETWEEN ? AND ?",
        (date_filter_start, date_filter_end))

    story.append(Paragraph("一、系统使用概况", styles['Heading2']))
    story.append(Paragraph(f"总访问次数：{total_visits:,}", styles['Normal']))
    story.append(Paragraph(f"总提问数：{total_questions:,}", styles['Normal']))
    story.append(Paragraph(f"活跃用户数：{unique_users:,}", styles['Normal']))
    story.append(Spacer(1, 0.3 * inch))

    df_trend = query_db("""
                        SELECT DATE (timestamp) as day, COUNT (*) as cnt
                        FROM visit_log
                        WHERE action ='提问' AND timestamp BETWEEN ? AND ?
                        GROUP BY day
                        ORDER BY day
                        """, (date_filter_start, date_filter_end))

    if not df_trend.empty:
        fig_trend = px.line(df_trend, x='day', y='cnt', markers=True,
                            labels={'day': '日期', 'cnt': '提问数'},
                            template='plotly_white')
        fig_trend.update_traces(line=dict(color='#4f46e5', width=2))
        fig_trend.update_layout(title="每日提问趋势", title_font=dict(family="Microsoft YaHei", size=18),
                                xaxis_title="", yaxis_title="提问量",
                                font=dict(family="Microsoft YaHei"))
        img_path = generate_chart_image(fig_trend, "trend")
        temp_files.append(img_path)
        story.append(Paragraph("二、提问趋势分析", styles['Heading2']))
        story.append(Image(img_path, width=6.5 * inch, height=3.2 * inch))
        story.append(Spacer(1, 0.3 * inch))

    try:
        df_subjects = query_db("""
                               SELECT subject, COUNT(*) as cnt
                               FROM question_analysis
                               WHERE subject != ''
                               GROUP BY subject
                               ORDER BY cnt DESC
                               """)
        if not df_subjects.empty:
            fig_pie = px.pie(df_subjects, names='subject', values='cnt', hole=0.4,
                             color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_pie.update_layout(title="热门知识点分布", title_font=dict(family="Microsoft YaHei", size=18),
                                  font=dict(family="Microsoft YaHei"))
            img_path = generate_chart_image(fig_pie, "subjects")
            temp_files.append(img_path)
            story.append(Paragraph("三、知识点分布", styles['Heading2']))
            story.append(Image(img_path, width=5.5 * inch, height=4 * inch))
            story.append(Spacer(1, 0.3 * inch))
    except:
        pass

    top_questions = query_db("""
                             SELECT detail, COUNT(*) as cnt
                             FROM visit_log
                             WHERE action ='提问' AND detail != '' AND timestamp BETWEEN ? AND ?
                             GROUP BY detail
                             ORDER BY cnt DESC LIMIT 10
                             """, (date_filter_start, date_filter_end))

    if not top_questions.empty:
        story.append(Paragraph("四、热门问题 Top 10", styles['Heading2']))
        for i, row in enumerate(top_questions.itertuples(index=False), 1):
            q = row[0]
            c = row[1]
            story.append(Paragraph(f"{i}. {q[:80]} — {c}次", styles['Normal']))
        story.append(Spacer(1, 0.3 * inch))

    df_gap = query_db("""
                      SELECT vl.detail, COUNT(*) as cnt
                      FROM visit_log vl
                               LEFT JOIN question_analysis qa ON vl.id = qa.visit_log_id
                      WHERE vl.action = '提问'
                        AND vl.timestamp BETWEEN ? AND ?
                        AND (qa.subject IS NULL OR qa.subject = '')
                      GROUP BY vl.detail
                      HAVING COUNT(*) >= 2
                      ORDER BY cnt DESC LIMIT 10
                      """, (date_filter_start, date_filter_end))

    if not df_gap.empty:
        story.append(Paragraph("五、知识库补充建议", styles['Heading2']))
        story.append(Paragraph("以下高频问题暂无知识库覆盖，建议补充：", styles['Normal']))
        for i, row in enumerate(df_gap.itertuples(index=False), 1):
            story.append(Paragraph(f"{i}. {row[0][:60]}  (提及{row[1]}次)", styles['Normal']))
        story.append(Spacer(1, 0.3 * inch))

    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph("— 报告由考研RAG运营分析平台自动生成 —",
                           ParagraphStyle('Footer', fontName=CN_FONT, fontSize=9, alignment=TA_CENTER,
                                          textColor=colors.grey)))

    doc.build(story)
    for f in temp_files:
        try:
            os.remove(f)
        except:
            pass
    return pdf_path