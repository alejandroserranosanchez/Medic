"""Insert the fictional clinicians only when their names are missing."""

from __future__ import annotations

from app.db import connect

CLINICIANS = ("Dr. Vega", "Dr. Nadal")


def seed_clinicians(conn=None) -> None:
    close = conn is None
    if conn is None:
        conn = connect()
    try:
        cursor = conn.cursor()
        for name in CLINICIANS:
            cursor.execute("SELECT id FROM dbo.clinicians WHERE display_name = %s", (name,))
            if cursor.fetchone() is None:
                cursor.execute("INSERT INTO dbo.clinicians (display_name) VALUES (%s)", (name,))
        conn.commit()
    finally:
        if close:
            conn.close()
