"""Apply numbered SQL files once and record them in this service's database."""

from __future__ import annotations

from pathlib import Path

from app.db import connect

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def split_batches(script: str) -> list[str]:
    batches: list[str] = []
    current: list[str] = []
    for line in script.splitlines():
        if line.strip().upper() == "GO":
            batches.append("\n".join(current))
            current = []
        else:
            current.append(line)
    batches.append("\n".join(current))
    return [batch.strip() for batch in batches if batch.strip()]


def apply_migrations(conn=None) -> list[str]:
    """Return the migration file names applied on this call. Already-applied files are skipped."""
    close = conn is None
    if conn is None:
        conn = connect()
    applied: list[str] = []
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            IF OBJECT_ID(N'dbo.schema_migrations', N'U') IS NULL
            CREATE TABLE dbo.schema_migrations (
                id NVARCHAR(200) NOT NULL PRIMARY KEY,
                applied_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
            )
            """
        )
        conn.commit()
        for path in sorted(MIGRATIONS.glob("*.sql")):
            cursor.execute("SELECT 1 FROM dbo.schema_migrations WHERE id = %s", (path.name,))
            if cursor.fetchone():
                continue
            for batch in split_batches(path.read_text(encoding="utf-8")):
                cursor.execute(batch)
            cursor.execute("INSERT INTO dbo.schema_migrations (id) VALUES (%s)", (path.name,))
            conn.commit()
            applied.append(path.name)
        return applied
    finally:
        if close:
            conn.close()
