"""SQLite connection helpers. One file path for the whole app."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app, g


def get_data_dir() -> Path:
    path = Path(current_app.config["DATA_DIR"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_db_path() -> Path:
    return get_data_dir() / current_app.config["DB_FILENAME"]


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_error=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db() -> None:
    """Create tables if missing. Never drops existing data."""
    schema_path = Path(current_app.root_path) / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    conn = get_db()
    conn.executescript(sql)
    conn.commit()
