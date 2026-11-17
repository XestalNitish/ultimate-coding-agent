"""Database module for the FastAPI Todo and Notes API.

Establishes SQLite connections and defines the tables used by the Todo and
Notes entities. All data access goes through the functions defined here so
that crud.py and main.py depend on a single, explicit interface.
"""

import sqlite3
from contextlib import contextmanager


@contextmanager
def get_db():
    """Provide a SQLite connection with row access by column name.

    The connection is committed on successful exit and closed on exit, so
    callers only need to use the connection as a context manager.
    """
    conn = sqlite3.connect("todo.db")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create the Todo and Notes tables if they do not already exist."""
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                completed BOOLEAN DEFAULT FALSE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


init_db()