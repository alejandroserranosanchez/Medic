"""Create one clinic booking in the Operations database.

The end time is calculated here. The caller chooses the session and the start time.
A new waiting-list request is saved in the same transaction because a booking belongs to one.
"""

from __future__ import annotations

from datetime import datetime

from app.rules import (
    BookingWindow,
    OperationsError,
    SessionWindow,
    booking_conflicts,
    booking_fits_session,
    compute_timing_plan,
    eligibility_issues,
)
from app.sessions import _row_to_dict
from app.timeutil import normalize_hhmm, normalize_label, parse_datetime_local


def _require_int(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OperationsError(f"{name} must be a whole number")
    return value


def _timing(cursor, clinician_id: int, procedure_code: str, start_time: str):
    cursor.execute(
        """
        SELECT code, duration_minutes, turnover_minutes, min_planning_minutes
        FROM dbo.procedure_types WHERE code = %s
        """,
        (procedure_code,),
    )
    procedure = cursor.fetchone()
    if procedure is None:
        raise OperationsError("unknown procedure")
    cursor.execute(
        """
        SELECT id, estimated_duration_minutes, variability_minutes
        FROM dbo.clinician_procedure_profiles
        WHERE clinician_id = %s AND procedure_code = %s
        """,
        (clinician_id, procedure_code),
    )
    profile = cursor.fetchone()
    if profile is not None:
        return compute_timing_plan(
            start_time=start_time,
            estimated_duration_minutes=int(profile["estimated_duration_minutes"]),
            variability_minutes=int(profile["variability_minutes"]),
            min_planning_minutes=int(procedure["min_planning_minutes"]),
            room_turnover_minutes=int(procedure["turnover_minutes"]),
            profile_id=int(profile["id"]),
            source="profile",
        )
    return compute_timing_plan(
        start_time=start_time,
        estimated_duration_minutes=int(procedure["duration_minutes"]),
        variability_minutes=0,
        min_planning_minutes=int(procedure["min_planning_minutes"]),
        room_turnover_minutes=int(procedure["turnover_minutes"]),
        profile_id=None,
        source="catalogue",
    )


def _booking(conn, booking_id: int, patient_ref: str) -> dict:
    cursor = conn.cursor(as_dict=True)
    cursor.execute(
        """
        SELECT id, request_id, session_id, start_time, end_time, status, timing_source,
               estimated_duration_minutes, variability_minutes, min_planning_minutes,
               planning_block_minutes, room_turnover_minutes
        FROM dbo.bookings WHERE id = %s
        """,
        (booking_id,),
    )
    row = cursor.fetchone()
    return {
        "id": int(row["id"]),
        "request_id": int(row["request_id"]),
        "session_id": int(row["session_id"]),
        "patient_ref": patient_ref,
        "procedure_code": None,
        "start_time": str(row["start_time"]).strip(),
        "end_time": str(row["end_time"]).strip(),
        "status": str(row["status"]).strip(),
        "timing_source": str(row["timing_source"]).strip(),
        "estimated_duration_minutes": int(row["estimated_duration_minutes"]),
        "variability_minutes": int(row["variability_minutes"]),
        "min_planning_minutes": int(row["min_planning_minutes"]),
        "planning_block_minutes": int(row["planning_block_minutes"]),
        "room_turnover_minutes": int(row["room_turnover_minutes"]),
    }


def create_booking(
    conn,
    *,
    session_id: int,
    start_time: str,
    patient_ref: str,
    procedure_code: str,
    priority: int,
    ready: bool,
    available_from: str,
    available_to: str,
    minimum_notice_minutes: int,
    requested_at: str,
    now: datetime | None = None,
) -> dict:
    session_key = _require_int(session_id, "session_id")
    rank = _require_int(priority, "priority")
    notice = _require_int(minimum_notice_minutes, "minimum_notice_minutes")
    if notice < 0:
        raise OperationsError("minimum notice cannot be negative")
    if not isinstance(ready, bool):
        raise OperationsError("ready must be true or false")
    patient = normalize_label(patient_ref)
    procedure = normalize_label(procedure_code).upper()
    start = normalize_hhmm(start_time)
    requested = parse_datetime_local(requested_at).strftime("%Y-%m-%dT%H:%M:%S")
    parse_datetime_local(available_from)
    parse_datetime_local(available_to)
    when = now or datetime.now().replace(microsecond=0)

    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute(
            """
            SELECT id, room_label, clinician_id, clinician_label,
                   CONVERT(char(10), session_date, 23) AS session_date,
                   start_time, end_time
            FROM dbo.sessions WITH (UPDLOCK, HOLDLOCK)
            WHERE id = %s
            """,
            (session_key,),
        )
        session_row = cursor.fetchone()
        if session_row is None:
            raise OperationsError("session not found", status=404)
        session = SessionWindow(**_row_to_dict(session_row))
        plan = _timing(cursor, session.clinician_id, procedure, start)
        issues = eligibility_issues(
            ready=ready,
            available_from=available_from,
            available_to=available_to,
            minimum_notice_minutes=notice,
            session_date=session.session_date,
            start_time=start,
            end_time=plan.end_time,
            now=when,
        )
        if issues:
            raise OperationsError("not eligible: " + ", ".join(issues))
        reason = booking_fits_session(session, start, plan.end_time, plan.room_turnover_minutes)
        if reason:
            raise OperationsError(reason)
        cursor.execute(
            """
            SELECT id, session_id, start_time, end_time, status, room_turnover_minutes
            FROM dbo.bookings WITH (UPDLOCK, HOLDLOCK)
            WHERE session_id = %s AND status IN (N'active', N'completed')
            """,
            (session_key,),
        )
        existing = [
            BookingWindow(
                id=int(row["id"]),
                session_id=int(row["session_id"]),
                start_time=str(row["start_time"]).strip(),
                end_time=str(row["end_time"]).strip(),
                status=str(row["status"]).strip(),
                room_turnover_minutes=int(row["room_turnover_minutes"]),
            )
            for row in cursor.fetchall()
        ]
        reason = booking_conflicts(start, plan.end_time, plan.room_turnover_minutes, existing)
        if reason:
            raise OperationsError(reason, status=409)
        cursor.execute(
            """
            INSERT INTO dbo.requests (
                patient_ref, procedure_code, priority, requested_at, ready,
                available_from, available_to, minimum_notice_minutes
            )
            OUTPUT INSERTED.id
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                patient,
                procedure,
                rank,
                requested,
                1 if ready else 0,
                parse_datetime_local(available_from).strftime("%Y-%m-%dT%H:%M:%S"),
                parse_datetime_local(available_to).strftime("%Y-%m-%dT%H:%M:%S"),
                notice,
            ),
        )
        request_id = int(cursor.fetchone()["id"])
        cursor.execute(
            """
            INSERT INTO dbo.bookings (
                request_id, session_id, start_time, end_time, status,
                profile_id, timing_source, estimated_duration_minutes, variability_minutes,
                min_planning_minutes, planning_block_minutes, room_turnover_minutes
            )
            OUTPUT INSERTED.id
            VALUES (%s, %s, %s, %s, N'active', %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                request_id,
                session_key,
                start,
                plan.end_time,
                plan.profile_id,
                plan.source,
                plan.estimated_duration_minutes,
                plan.variability_minutes,
                plan.min_planning_minutes,
                plan.planning_block_minutes,
                plan.room_turnover_minutes,
            ),
        )
        booking_id = int(cursor.fetchone()["id"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    saved = _booking(conn, booking_id, patient)
    saved["procedure_code"] = procedure
    return saved
