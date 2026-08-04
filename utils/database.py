import os
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_memory_db_path():
    configured = os.environ.get("MEMORY_DB", "").strip()
    path = Path(configured) if configured else PROJECT_ROOT / "data" / "memory.db"
    return path if path.is_absolute() else PROJECT_ROOT / path


MEMORY_DB = str(get_memory_db_path())

def query_db(sql, params=(), as_df=False):
    conn = sqlite3.connect(MEMORY_DB)
    try:
        if as_df:
            import pandas as pd

            return pd.read_sql_query(sql, conn, params=params)
        c = conn.cursor()
        c.execute(sql, params)
        return c.fetchall()
    finally:
        conn.close()

def get_single_value(sql, params=()):
    conn = sqlite3.connect(MEMORY_DB)
    try:
        c = conn.cursor()
        c.execute(sql, params)
        row = c.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()
