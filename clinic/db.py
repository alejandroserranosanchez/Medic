"""SQLite connection helpers + idempotent migrations for existing databases."""

from __future__ import annotations

import sqlite3
from datetime import datetime
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
        conn = sqlite3.connect(get_db_path(), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_error=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migration_applied(conn: sqlite3.Connection, migration_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 AS ok FROM schema_migrations WHERE id = ?",
        (migration_id,),
    ).fetchone()
    return row is not None


def _mark_migration(conn: sqlite3.Connection, migration_id: str) -> None:
    conn.execute(
        "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)",
        (migration_id, datetime.now().replace(microsecond=0).isoformat(sep="T")),
    )


def migrate(conn: sqlite3.Connection) -> None:
    """Upgrade older local DBs without deleting data."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )

    migration_id = "2026-10-09-profiles-snapshots"
    if _migration_applied(conn, migration_id):
        return

    conn.execute("BEGIN IMMEDIATE")
    try:
        # Fresh installs already have full schema.sql; only patch older files.
        cols = _table_columns(conn, "procedure_types") if _table_exists(conn, "procedure_types") else set()
        if cols and "min_planning_minutes" not in cols:
            conn.execute(
                "ALTER TABLE procedure_types ADD COLUMN min_planning_minutes INTEGER NOT NULL DEFAULT 30"
            )
            conn.execute(
                "UPDATE procedure_types SET min_planning_minutes = duration_minutes "
                "WHERE min_planning_minutes IS NULL OR min_planning_minutes = 30"
            )
            # Prefer catalogue duration as centre minimum for existing rows.
            conn.execute("UPDATE procedure_types SET min_planning_minutes = duration_minutes")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clinicians (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL UNIQUE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clinician_procedure_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clinician_id INTEGER NOT NULL REFERENCES clinicians(id),
                procedure_code TEXT NOT NULL REFERENCES procedure_types(code),
                estimated_duration_minutes INTEGER NOT NULL CHECK (estimated_duration_minutes > 0),
                variability_minutes INTEGER NOT NULL CHECK (variability_minutes >= 0),
                estimate_origin TEXT NOT NULL,
                reviewed_on TEXT NOT NULL,
                UNIQUE (clinician_id, procedure_code)
            )
            """
        )

        session_cols = _table_columns(conn, "sessions") if _table_exists(conn, "sessions") else set()
        if session_cols and "clinician_id" not in session_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN clinician_id INTEGER REFERENCES clinicians(id)")

        booking_cols = _table_columns(conn, "bookings") if _table_exists(conn, "bookings") else set()
        if booking_cols:
            additions = {
                "profile_id": "INTEGER",
                "timing_source": "TEXT NOT NULL DEFAULT 'catalogue'",
                "estimated_duration_minutes": "INTEGER NOT NULL DEFAULT 0",
                "variability_minutes": "INTEGER NOT NULL DEFAULT 0",
                "min_planning_minutes": "INTEGER NOT NULL DEFAULT 0",
                "planning_block_minutes": "INTEGER NOT NULL DEFAULT 0",
                "room_turnover_minutes": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, decl in additions.items():
                if name not in booking_cols:
                    conn.execute(f"ALTER TABLE bookings ADD COLUMN {name} {decl}")

            # Backfill snapshots from current catalogue (reconstruction only).
            conn.execute(
                """
                UPDATE bookings
                SET
                    timing_source = 'catalogue',
                    estimated_duration_minutes = (
                        SELECT p.duration_minutes FROM requests r
                        JOIN procedure_types p ON p.code = r.procedure_code
                        WHERE r.id = bookings.request_id
                    ),
                    variability_minutes = 0,
                    room_turnover_minutes = (
                        SELECT p.turnover_minutes FROM requests r
                        JOIN procedure_types p ON p.code = r.procedure_code
                        WHERE r.id = bookings.request_id
                    ),
                    min_planning_minutes = (
                        SELECT COALESCE(p.min_planning_minutes, p.duration_minutes)
                        FROM requests r
                        JOIN procedure_types p ON p.code = r.procedure_code
                        WHERE r.id = bookings.request_id
                    ),
                    planning_block_minutes = (
                        SELECT COALESCE(p.min_planning_minutes, p.duration_minutes)
                        FROM requests r
                        JOIN procedure_types p ON p.code = r.procedure_code
                        WHERE r.id = bookings.request_id
                    )
                WHERE planning_block_minutes = 0 OR estimated_duration_minutes = 0
                """
            )

        _mark_migration(conn, migration_id)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def init_db() -> None:
    """Create tables if missing, then migrate. Never drops existing data."""
    schema_path = Path(current_app.root_path) / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    conn = get_db()
    conn.executescript(sql)
    migrate(conn)
