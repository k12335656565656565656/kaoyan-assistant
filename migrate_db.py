"""数据库升级脚本 —— 运行一次即可"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "memory.db")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# ─── 新建表（不修改 visit_log 和 suggestions） ───

# 1. 问题分析表
cursor.execute("""
CREATE TABLE IF NOT EXISTS question_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_log_id INTEGER UNIQUE,
    question_text TEXT NOT NULL,
    subject TEXT DEFAULT '',
    chapter TEXT DEFAULT '',
    knowledge_point TEXT DEFAULT '',
    difficulty TEXT DEFAULT '未分类',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (visit_log_id) REFERENCES visit_log(id)
)
""")

# 2. RAG 回答记录表
cursor.execute("""
CREATE TABLE IF NOT EXISTS rag_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER,
    retrieved_docs TEXT DEFAULT '',
    top_similarity REAL DEFAULT 0.0,
    answer_text TEXT DEFAULT '',
    response_time_ms INTEGER DEFAULT 0,
    token_used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (question_id) REFERENCES question_analysis(id)
)
""")

# 3. 用户反馈表
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER,
    username TEXT,
    rating TEXT DEFAULT '',
    comment TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (question_id) REFERENCES question_analysis(id)
)
""")

# 4. 自动分类缓存表（避免重复调用 LLM）
cursor.execute("""
CREATE TABLE IF NOT EXISTS classification_cache (
    question_hash TEXT PRIMARY KEY,
    subject TEXT,
    chapter TEXT,
    knowledge_point TEXT,
    difficulty TEXT,
    classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()
conn.close()
print("✅ 数据库升级完成！新增4张表：question_analysis, rag_record, user_feedback, classification_cache")
print("📌 原有 visit_log 和 suggestions 表数据完好无损")