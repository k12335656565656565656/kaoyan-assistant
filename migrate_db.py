"""Create the optional admin analytics tables without running on import."""

from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4

from utils.database import MEMORY_DB


def migrate(db_path=None, create_backup=True):
    path = Path(db_path or MEMORY_DB).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = None
    if create_backup and path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup_path = path.with_name(f"{path.name}.bak-{stamp}-{uuid4().hex[:8]}")
        shutil.copy2(path, backup_path)

    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            """
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
            );
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
            );
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER,
                username TEXT,
                rating TEXT DEFAULT '',
                comment TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (question_id) REFERENCES question_analysis(id)
            );
            CREATE TABLE IF NOT EXISTS classification_cache (
                question_hash TEXT PRIMARY KEY,
                subject TEXT,
                chapter TEXT,
                knowledge_point TEXT,
                difficulty TEXT,
                classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.commit()
    finally:
        connection.close()
    return {"database": str(path), "backup": str(backup_path) if backup_path else ""}


if __name__ == "__main__":
    result = migrate()
    print(f"Admin analytics migration complete: {result['database']}")
    if result["backup"]:
        print(f"Backup created: {result['backup']}")
