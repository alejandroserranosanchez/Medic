"""Deterministic fictional seed. Runs only on an empty procedure_types table."""

from __future__ import annotations

from datetime import timedelta

from clinic.clock import now as clock_now
from clinic.db import get_db


def seed_if_empty() -> None:
    db = get_db()
    row = db.execute("SELECT COUNT(*) AS n FROM procedure_types").fetchone()
    if row["n"] > 0:
        return

    # Demo session is always "tomorrow" so a fresh start has bookable slots.
    today = clock_now().date()
    day = (today + timedelta(days=1)).isoformat()
    yesterday = (today - timedelta(days=1)).isoformat()

    db.execute("BEGIN IMMEDIATE")
    try:
        db.executemany(
            """
            INSERT INTO procedure_types (
                code, display_name, duration_minutes, turnover_minutes, min_planning_minutes
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                # Catalogue defaults: SEPD-like 30/45 blocks; turnover is a fictional room buffer.
                ("GASTRO", "Gastroscopy", 30, 10, 30),
                ("COLONO", "Colonoscopy", 45, 15, 45),
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

        # Two fictional clinicians with different GASTRO profiles (guide §6.5 example).
        db.execute("INSERT INTO clinicians (display_name) VALUES (?)", ("Dr. Vega",))
        vega_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("INSERT INTO clinicians (display_name) VALUES (?)", ("Dr. Nadal",))
        nadal_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        db.executemany(
            """
            INSERT INTO clinician_procedure_profiles (
                clinician_id, procedure_code, estimated_duration_minutes, variability_minutes,
                estimate_origin, reviewed_on
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (vega_id, "GASTRO", 25, 5, "fictional centre agreement", "2026-10-01"),
                (nadal_id, "GASTRO", 35, 5, "fictional centre agreement", "2026-10-01"),
                # COLONO uses catalogue when no profile row is needed for demo simplicity.
            ],
        )

        db.execute(
            """
            INSERT INTO sessions (
                room_label, clinician_id, clinician_label, session_date, start_time, end_time
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("Room A", vega_id, "Dr. Vega", day, "09:00", "12:00"),
        )
        session_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        insert_request = """
            INSERT INTO requests (
                patient_ref, procedure_code, priority, requested_at, ready,
                available_from, available_to, minimum_notice_minutes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        db.execute(
            insert_request,
            ("P-1001", "GASTRO", 2, f"{yesterday}T08:00:00", 1,
             f"{day}T09:00:00", f"{day}T18:00:00", 60),
        )
        request_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Waiting list: one eligible, one not ready, one only free in the afternoon.
        db.executemany(
            insert_request,
            [
                ("P-1002", "GASTRO", 3, f"{yesterday}T09:30:00", 1,
                 f"{day}T09:00:00", f"{day}T13:00:00", 60),
                ("P-1003", "GASTRO", 3, f"{yesterday}T10:00:00", 0,
                 f"{day}T09:00:00", f"{day}T18:00:00", 60),
                ("P-1004", "COLONO", 1, f"{yesterday}T11:00:00", 1,
                 f"{day}T14:00:00", f"{day}T18:00:00", 120),
            ],
        )

        # Vega GASTRO: max(30, 25+5)=30 block + 10 room => occupies until 09:40.
        profile = db.execute(
            """
            SELECT id FROM clinician_procedure_profiles
            WHERE clinician_id = ? AND procedure_code = 'GASTRO'
            """,
            (vega_id,),
        ).fetchone()
        db.execute(
            """
            INSERT INTO bookings (
                request_id, session_id, start_time, end_time, status,
                profile_id, timing_source,
                estimated_duration_minutes, variability_minutes,
                min_planning_minutes, planning_block_minutes, room_turnover_minutes
            ) VALUES (?, ?, ?, ?, 'active', ?, 'profile', 25, 5, 30, 30, 10)
            """,
            (request_id, session_id, "09:00", "09:30", profile["id"]),
        )

        # Yesterday's session: a booking that has already happened, ready to be marked done.
        # Nadal GASTRO: max(30, 35+5)=40 block + 10 room.
        db.execute(
            """
            INSERT INTO sessions (
                room_label, clinician_id, clinician_label, session_date, start_time, end_time
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("Room B", nadal_id, "Dr. Nadal", yesterday, "09:00", "12:00"),
        )
        past_session_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute(
            insert_request,
            ("P-0901", "GASTRO", 2, f"{yesterday}T07:00:00", 1,
             f"{yesterday}T08:00:00", f"{yesterday}T12:00:00", 0),
        )
        past_request_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        nadal_profile = db.execute(
            """
            SELECT id FROM clinician_procedure_profiles
            WHERE clinician_id = ? AND procedure_code = 'GASTRO'
            """,
            (nadal_id,),
        ).fetchone()
        db.execute(
            """
            INSERT INTO bookings (
                request_id, session_id, start_time, end_time, status,
                profile_id, timing_source,
                estimated_duration_minutes, variability_minutes,
                min_planning_minutes, planning_block_minutes, room_turnover_minutes
            ) VALUES (?, ?, ?, ?, 'active', ?, 'profile', 35, 5, 30, 40, 10)
            """,
            (past_request_id, past_session_id, "09:00", "09:40", nadal_profile["id"]),
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
