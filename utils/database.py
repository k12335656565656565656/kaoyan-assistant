import sqlite3
import os
import pandas as pd

MEMORY_DB = os.path.join(os.path.dirname(__file__), "..", "data", "memory.db")

def query_db(sql, params=(), as_df=False):
    conn = sqlite3.connect(MEMORY_DB)
    if as_df:
        df = pd.read_sql_query(sql, conn, params=params)
        conn.close()
        return df
    else:
        c = conn.cursor()
        c.execute(sql, params)
        rows = c.fetchall()
        conn.close()
        return rows

def get_single_value(sql, params=()):
    conn = sqlite3.connect(MEMORY_DB)
    c = conn.cursor()
    c.execute(sql, params)
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0