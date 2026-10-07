"""Deterministic fictional seed. Runs only on an empty procedure_types table."""

from __future__ import annotations

from clinic.db import get_db


def seed_if_empty() -> None:
    db = get_db()
    row = db.execute("SELECT COUNT(*) AS n FROM procedure_types").fetchone()
    if row["n"] > 0:
        return

    db.executemany(
        """
        INSERT INTO procedure_types (code, display_name, duration_minutes, turnover_minutes)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("GASTRO", "Gastroscopy", 30, 10),
            ("COLONO", "Colonoscopy", 45, 15),
        ],
    )
    db.executemany(
        """
        INSERT INTO fee_assumptions (procedure_code, expected_fee_cents, variable_cost_cents)
        VALUES (?, ?, ?)
        """,
        [
            ("GASTRO", 12000, 2500),
            ("COLONO", 18000, 4000),
        ],
    )
    db.execute(
        """
        INSERT INTO sessions (room_label, clinician_label, session_date, start_time, end_time)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("Room A", "Dr. Vega", "2026-10-10", "09:00", "12:00"),
    )
    db.execute(
        """
        INSERT INTO requests (
            patient_ref, procedure_code, priority, requested_at, ready,
            available_from, available_to, minimum_notice_minutes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "P-1001",
            "GASTRO",
            2,
            "2026-10-08T08:00:00",
            1,
            "2026-10-10T09:00:00",
            "2026-10-10T18:00:00",
            60,
        ),
    )
    request_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    session_id = db.execute("SELECT id FROM sessions ORDER BY id LIMIT 1").fetchone()["id"]
    db.execute(
        """
        INSERT INTO bookings (request_id, session_id, start_time, end_time, status)
        VALUES (?, ?, ?, ?, 'active')
        """,
        (request_id, session_id, "09:00", "09:30"),
    )
    db.commit()
