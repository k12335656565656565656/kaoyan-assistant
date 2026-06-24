import sqlite3
from contextlib import contextmanager


@contextmanager
def connect(db_path, *, row_factory=sqlite3.Row):
    conn = sqlite3.connect(db_path)
    if row_factory is not None:
        conn.row_factory = row_factory
    try:
        yield conn
    finally:
        conn.close()
