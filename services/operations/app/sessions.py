"""Read and write sessions in the Operations database."""

from __future__ import annotations

from app.rules import OperationsError, SessionWindow, session_conflicts
from app.timeutil import normalize_hhmm, normalize_label, validate_iso_date


def _row_to_dict(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "room_label": str(row["room_label"]).strip(),
        "clinician_id": int(row["clinician_id"]),
        "clinician_label": str(row["clinician_label"]).strip(),
        "session_date": str(row["session_date"])[:10],
        "start_time": str(row["start_time"]).strip(),
        "end_time": str(row["end_time"]).strip(),
    }


def _window(row: dict) -> SessionWindow:
    item = _row_to_dict(row)
    return SessionWindow(
        id=item["id"],
        room_label=item["room_label"],
        clinician_label=item["clinician_label"],
        session_date=item["session_date"],
        start_time=item["start_time"],
        end_time=item["end_time"],
        clinician_id=item["clinician_id"],
    )


_SELECT = """
SELECT id, room_label, clinician_id, clinician_label,
       CONVERT(char(10), session_date, 23) AS session_date,
       start_time, end_time
FROM dbo.sessions
"""


def list_sessions(conn) -> list[dict]:
    cursor = conn.cursor(as_dict=True)
    cursor.execute(_SELECT + " ORDER BY session_date, start_time, id")
    return [_row_to_dict(row) for row in cursor.fetchall()]


def get_session(conn, session_id: int) -> dict:
    cursor = conn.cursor(as_dict=True)
    cursor.execute(_SELECT + " WHERE id = %s", (session_id,))
    row = cursor.fetchone()
    if row is None:
        raise OperationsError("session not found", status=404)
    return _row_to_dict(row)


def _clinician(conn, clinician_id: int | None, clinician_label: str | None) -> tuple[int, str]:
    cursor = conn.cursor(as_dict=True)
    if clinician_id is not None:
        cursor.execute(
            "SELECT id, display_name FROM dbo.clinicians WHERE id = %s",
            (clinician_id,),
        )
    else:
        label = normalize_label(clinician_label or "")
        cursor.execute(
            "SELECT id, display_name FROM dbo.clinicians WHERE LOWER(display_name) = LOWER(%s)",
            (label,),
        )
    row = cursor.fetchone()
    if row is None:
        raise OperationsError("clinician not found", status=404)
    return int(row["id"]), str(row["display_name"])


def create_session(
    conn,
    *,
    room_label: str,
    session_date: str,
    start_time: str,
    end_time: str,
    clinician_id: int | None = None,
    clinician_label: str | None = None,
) -> dict:
    room = normalize_label(room_label)
    day = validate_iso_date(session_date)
    start = normalize_hhmm(start_time)
    end = normalize_hhmm(end_time)
    if start >= end:
        raise OperationsError("session end must be after start")
    try:
        clinician_key, clinician_name = _clinician(conn, clinician_id, clinician_label)
        cursor = conn.cursor(as_dict=True)
        cursor.execute(_SELECT + " WITH (UPDLOCK, HOLDLOCK)")
        existing = [_window(row) for row in cursor.fetchall()]
        candidate = SessionWindow(
            id=-1,
            room_label=room,
            clinician_label=clinician_name,
            session_date=day,
            start_time=start,
            end_time=end,
            clinician_id=clinician_key,
        )
        reason = session_conflicts(candidate, existing)
        if reason:
            raise OperationsError(reason, status=409)
        cursor.execute(
            """
            INSERT INTO dbo.sessions (
                room_label, clinician_id, clinician_label, session_date, start_time, end_time
            )
            OUTPUT INSERTED.id
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (room, clinician_key, clinician_name, day, start, end),
        )
        new_id = int(cursor.fetchone()["id"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_session(conn, new_id)
