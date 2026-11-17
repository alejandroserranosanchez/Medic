"""Insert clinicians and the procedure catalogue only when those rows are missing."""

from __future__ import annotations

from app.db import connect

CLINICIANS = ("Dr. Vega", "Dr. Nadal")

# Catalogue durations from the original clinic: gastroscopy 30, colonoscopy 45.
PROCEDURES = (
    ("GASTRO", "Gastroscopy", 30, 10, 30),
    ("COLONO", "Colonoscopy", 45, 15, 45),
)

# Clinician agreements from the original clinic. Vega's gastroscopy block stays 30.
# Nadal's estimate plus variability is 40, which is above the 30-minute minimum.
PROFILES = (
    ("Dr. Vega", "GASTRO", 25, 5, "fictional centre agreement", "2026-10-01"),
    ("Dr. Nadal", "GASTRO", 35, 5, "fictional centre agreement", "2026-10-01"),
)


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


def seed_catalogue(conn=None) -> None:
    close = conn is None
    if conn is None:
        conn = connect()
    try:
        cursor = conn.cursor()
        for code, name, duration, turnover, minimum in PROCEDURES:
            cursor.execute("SELECT code FROM dbo.procedure_types WHERE code = %s", (code,))
            if cursor.fetchone() is None:
                cursor.execute(
                    """
                    INSERT INTO dbo.procedure_types (
                        code, display_name, duration_minutes, turnover_minutes, min_planning_minutes
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (code, name, duration, turnover, minimum),
                )
        for clinician, code, estimate, variability, origin, reviewed in PROFILES:
            cursor.execute(
                """
                SELECT profiles.id
                FROM dbo.clinician_procedure_profiles AS profiles
                JOIN dbo.clinicians AS clinicians ON clinicians.id = profiles.clinician_id
                WHERE clinicians.display_name = %s AND profiles.procedure_code = %s
                """,
                (clinician, code),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    """
                    INSERT INTO dbo.clinician_procedure_profiles (
                        clinician_id, procedure_code, estimated_duration_minutes,
                        variability_minutes, estimate_origin, reviewed_on
                    )
                    SELECT id, %s, %s, %s, %s, %s FROM dbo.clinicians WHERE display_name = %s
                    """,
                    (code, estimate, variability, origin, reviewed, clinician),
                )
        conn.commit()
    finally:
        if close:
            conn.close()
