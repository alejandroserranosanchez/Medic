"""Deterministic fictional seed. Runs only on an empty procedure_types table."""

from __future__ import annotations

from clinic.db import get_db


def seed_if_empty() -> None:
    db = get_db()
    row = db.execute("SELECT COUNT(*) AS n FROM procedure_types").fetchone()
    if row["n"] > 0:
        return

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
            ("Room A", vega_id, "Dr. Vega", "2026-10-10", "09:00", "12:00"),
        )
        session_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

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
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
