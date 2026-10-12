"""SQLite access for operations. Write helpers do not nest commits; callers own BEGIN IMMEDIATE."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from clinic.clock import now as clock_now
from clinic.operations.service import (
    BookingWindow,
    OperationsError,
    SessionWindow,
    TimingPlan,
    booking_conflicts,
    booking_fits_session,
    can_cancel,
    compute_timing_plan,
    eligibility_issues,
    free_gaps,
    session_conflicts,
)
from clinic.timeutil import (
    add_minutes_hhmm,
    normalize_hhmm,
    normalize_label,
    parse_datetime_local,
    validate_iso_date,
)


def list_clinicians(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT id, display_name FROM clinicians ORDER BY display_name, id"
    ).fetchall()


def list_sessions(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        """
        SELECT id, room_label, clinician_id, clinician_label, session_date, start_time, end_time
        FROM sessions
        ORDER BY session_date, start_time, id
        """
    ).fetchall()


def list_bookings(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        """
        SELECT
            b.id,
            b.request_id,
            b.session_id,
            b.start_time,
            b.end_time,
            b.status,
            b.profile_id,
            b.timing_source,
            b.estimated_duration_minutes,
            b.variability_minutes,
            b.min_planning_minutes,
            b.planning_block_minutes,
            b.room_turnover_minutes,
            r.patient_ref,
            r.procedure_code,
            s.room_label,
            s.clinician_label,
            s.session_date
        FROM bookings b
        JOIN requests r ON r.id = b.request_id
        JOIN sessions s ON s.id = b.session_id
        ORDER BY s.session_date, b.start_time, b.id
        """
    ).fetchall()


def list_requests(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        """
        SELECT id, patient_ref, procedure_code, priority, ready, requested_at,
               available_from, available_to, minimum_notice_minutes
        FROM requests
        ORDER BY priority DESC, requested_at ASC, id ASC
        """
    ).fetchall()


def list_waiting_requests(db: sqlite3.Connection) -> list[sqlite3.Row]:
    """Requests with no active/completed booking, in recovery ranking order."""
    return db.execute(
        """
        SELECT r.id, r.patient_ref, r.procedure_code, r.priority, r.ready, r.requested_at,
               r.available_from, r.available_to, r.minimum_notice_minutes
        FROM requests r
        WHERE NOT EXISTS (
            SELECT 1 FROM bookings b
            WHERE b.request_id = r.id AND b.status IN ('active', 'completed')
        )
        ORDER BY r.priority DESC, r.requested_at ASC, r.id ASC
        """
    ).fetchall()


def get_booking(db: sqlite3.Connection, booking_id: int) -> sqlite3.Row | None:
    return db.execute(
        "SELECT id, session_id, start_time, end_time, status FROM bookings WHERE id = ?",
        (booking_id,),
    ).fetchone()


def list_procedure_types(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        """
        SELECT code, display_name, duration_minutes, turnover_minutes, min_planning_minutes
        FROM procedure_types
        ORDER BY code
        """
    ).fetchall()


def count_waiting_requests(db: sqlite3.Connection) -> int:
    """Waiting = no active booking and no completed booking."""
    row = db.execute(
        """
        SELECT COUNT(*) AS n
        FROM requests r
        WHERE NOT EXISTS (
            SELECT 1 FROM bookings b
            WHERE b.request_id = r.id AND b.status IN ('active', 'completed')
        )
        """
    ).fetchone()
    return int(row["n"])


def _session_windows(db: sqlite3.Connection) -> list[SessionWindow]:
    return [
        SessionWindow(
            id=row["id"],
            room_label=row["room_label"],
            clinician_label=row["clinician_label"],
            session_date=row["session_date"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            clinician_id=row["clinician_id"],
        )
        for row in list_sessions(db)
    ]


def _resolve_clinician(db: sqlite3.Connection, clinician_id: int | None, clinician_label: str | None) -> tuple[int, str]:
    if clinician_id is not None:
        row = db.execute(
            "SELECT id, display_name FROM clinicians WHERE id = ?",
            (clinician_id,),
        ).fetchone()
        if row is None:
            raise OperationsError("clinician not found")
        return int(row["id"]), row["display_name"]

    label = normalize_label(clinician_label or "")
    row = db.execute(
        "SELECT id, display_name FROM clinicians WHERE lower(display_name) = lower(?)",
        (label,),
    ).fetchone()
    if row is None:
        raise OperationsError(
            f"unknown clinician {label!r}; choose an existing clinician (profiles live per doctor)"
        )
    return int(row["id"]), row["display_name"]


def create_session(
    db: sqlite3.Connection,
    *,
    room_label: str,
    session_date: str,
    start_time: str,
    end_time: str,
    clinician_id: int | None = None,
    clinician_label: str | None = None,
) -> int:
    room = normalize_label(room_label)
    day = validate_iso_date(session_date)
    start = normalize_hhmm(start_time)
    end = normalize_hhmm(end_time)
    cid, clabel = _resolve_clinician(db, clinician_id, clinician_label)

    candidate = SessionWindow(
        id=-1,
        room_label=room,
        clinician_label=clabel,
        session_date=day,
        start_time=start,
        end_time=end,
        clinician_id=cid,
    )

    db.execute("BEGIN IMMEDIATE")
    try:
        reason = session_conflicts(candidate, _session_windows(db))
        if reason:
            raise OperationsError(reason)
        cur = db.execute(
            """
            INSERT INTO sessions (
                room_label, clinician_id, clinician_label, session_date, start_time, end_time
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (room, cid, clabel, day, start, end),
        )
        db.execute("COMMIT")
        return int(cur.lastrowid)
    except Exception:
        db.execute("ROLLBACK")
        raise


def create_request(
    db: sqlite3.Connection,
    *,
    patient_ref: str,
    procedure_code: str,
    priority: int,
    requested_at: str,
    ready: bool,
    available_from: str,
    available_to: str,
    minimum_notice_minutes: int,
) -> int:
    ref = normalize_label(patient_ref)
    if int(priority) < 0 or int(priority) > 10:
        raise OperationsError("priority must be between 0 and 10")
    notice = int(minimum_notice_minutes)
    if notice < 0:
        raise OperationsError("minimum notice cannot be negative")

    exists = db.execute(
        "SELECT 1 FROM procedure_types WHERE code = ?",
        (procedure_code,),
    ).fetchone()
    if exists is None:
        raise OperationsError(f"unknown procedure code: {procedure_code}")

    # Validate datetime formats early (clear domain error, not IntegrityError/500).
    parse_datetime_local(requested_at)
    avail_from = parse_datetime_local(available_from)
    avail_to = parse_datetime_local(available_to)
    if avail_from >= avail_to:
        raise OperationsError("available_from must be before available_to")

    db.execute("BEGIN IMMEDIATE")
    try:
        cur = db.execute(
            """
            INSERT INTO requests (
                patient_ref, procedure_code, priority, requested_at, ready,
                available_from, available_to, minimum_notice_minutes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ref,
                procedure_code,
                int(priority),
                requested_at.strip(),
                1 if ready else 0,
                available_from.strip(),
                available_to.strip(),
                notice,
            ),
        )
        db.execute("COMMIT")
        return int(cur.lastrowid)
    except sqlite3.IntegrityError as exc:
        db.execute("ROLLBACK")
        raise OperationsError(f"could not save request: {exc}") from exc
    except Exception:
        db.execute("ROLLBACK")
        raise


def _timing_for_session_procedure(
    db: sqlite3.Connection,
    *,
    clinician_id: int | None,
    procedure_code: str,
    start_time: str,
) -> TimingPlan:
    procedure = db.execute(
        """
        SELECT code, duration_minutes, turnover_minutes, min_planning_minutes
        FROM procedure_types WHERE code = ?
        """,
        (procedure_code,),
    ).fetchone()
    if procedure is None:
        raise OperationsError("unknown procedure")

    profile = None
    if clinician_id is not None:
        profile = db.execute(
            """
            SELECT id, estimated_duration_minutes, variability_minutes
            FROM clinician_procedure_profiles
            WHERE clinician_id = ? AND procedure_code = ?
            """,
            (clinician_id, procedure_code),
        ).fetchone()

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


def _booking_windows(db: sqlite3.Connection, session_id: int) -> list[BookingWindow]:
    rows = db.execute(
        """
        SELECT id, session_id, start_time, end_time, status, room_turnover_minutes
        FROM bookings
        WHERE session_id = ? AND status IN ('active', 'completed')
        """,
        (session_id,),
    ).fetchall()
    return [
        BookingWindow(
            id=row["id"],
            session_id=row["session_id"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            status=row["status"],
            room_turnover_minutes=int(row["room_turnover_minutes"] or 0),
        )
        for row in rows
    ]


def _session_window(row: sqlite3.Row) -> SessionWindow:
    return SessionWindow(
        id=row["id"],
        room_label=row["room_label"],
        clinician_label=row["clinician_label"],
        session_date=row["session_date"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        clinician_id=row["clinician_id"],
    )


def list_schedule(db: sqlite3.Connection) -> list[dict]:
    """Each session with its bookings and the free gaps left between them."""
    bookings = list_bookings(db)
    schedule = []
    for session in list_sessions(db):
        own = [b for b in bookings if b["session_id"] == session["id"]]
        occupied = [
            (b["start_time"], add_minutes_hhmm(b["end_time"], int(b["room_turnover_minutes"] or 0)))
            for b in own
            if b["status"] in ("active", "completed")
        ]
        schedule.append(
            {
                "session": session,
                "bookings": own,
                "gaps": free_gaps(session["start_time"], session["end_time"], occupied),
            }
        )
    return schedule


def slot_candidates(
    db: sqlite3.Connection,
    *,
    session_id: int,
    start_time: str,
    now: datetime | None = None,
) -> list[dict]:
    """Waiting requests checked against one start time. Read-only: nothing is reserved."""
    start = normalize_hhmm(start_time)
    when = now or clock_now()
    row = db.execute(
        """
        SELECT id, room_label, clinician_id, clinician_label, session_date, start_time, end_time
        FROM sessions WHERE id = ?
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        raise OperationsError("session not found")
    session = _session_window(row)
    existing = _booking_windows(db, session_id)

    candidates = []
    for req in list_waiting_requests(db):
        try:
            plan = _timing_for_session_procedure(
                db,
                clinician_id=session.clinician_id,
                procedure_code=req["procedure_code"],
                start_time=start,
            )
        except ValueError:
            continue
        issues = eligibility_issues(
            ready=bool(req["ready"]),
            available_from=req["available_from"],
            available_to=req["available_to"],
            minimum_notice_minutes=int(req["minimum_notice_minutes"]),
            session_date=session.session_date,
            start_time=start,
            end_time=plan.end_time,
            now=when,
            has_active_booking=False,
            has_completed_booking=False,
        )
        if booking_fits_session(session, start, plan.end_time, plan.room_turnover_minutes):
            issues.append("does_not_fit")
        elif booking_conflicts(start, plan.end_time, plan.room_turnover_minutes, existing):
            issues.append("overlaps_booking")
        candidates.append(
            {
                "request": req,
                "start_time": start,
                "end_time": plan.end_time,
                "occupied_end_time": plan.occupied_end_time,
                "issues": issues,
            }
        )
    # Eligible first; within each group keep the ranking order (priority, then oldest request).
    return sorted(candidates, key=lambda c: bool(c["issues"]))


def create_booking(
    db: sqlite3.Connection,
    *,
    request_id: int,
    session_id: int,
    start_time: str,
    now: datetime | None = None,
) -> int:
    """Create a booking. End time is computed on the server from profile/catalogue."""
    start = normalize_hhmm(start_time)
    when = now or clock_now()

    db.execute("BEGIN IMMEDIATE")
    try:
        request = db.execute(
            """
            SELECT r.*, p.code AS procedure_code
            FROM requests r
            JOIN procedure_types p ON p.code = r.procedure_code
            WHERE r.id = ?
            """,
            (request_id,),
        ).fetchone()
        if request is None:
            raise OperationsError("request not found")

        active = db.execute(
            "SELECT id FROM bookings WHERE request_id = ? AND status = 'active'",
            (request_id,),
        ).fetchone()
        completed = db.execute(
            "SELECT id FROM bookings WHERE request_id = ? AND status = 'completed'",
            (request_id,),
        ).fetchone()

        session_row = db.execute(
            """
            SELECT id, room_label, clinician_id, clinician_label, session_date, start_time, end_time
            FROM sessions WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        if session_row is None:
            raise OperationsError("session not found")

        plan = _timing_for_session_procedure(
            db,
            clinician_id=session_row["clinician_id"],
            procedure_code=request["procedure_code"],
            start_time=start,
        )

        issues = eligibility_issues(
            ready=bool(request["ready"]),
            available_from=request["available_from"],
            available_to=request["available_to"],
            minimum_notice_minutes=int(request["minimum_notice_minutes"]),
            session_date=session_row["session_date"],
            start_time=start,
            end_time=plan.end_time,
            now=when,
            has_active_booking=active is not None,
            has_completed_booking=completed is not None,
        )
        if issues:
            raise OperationsError("not eligible: " + ", ".join(issues))

        session = _session_window(session_row)
        reason = booking_fits_session(
            session, start, plan.end_time, plan.room_turnover_minutes
        )
        if reason:
            raise OperationsError(reason)

        reason = booking_conflicts(
            start, plan.end_time, plan.room_turnover_minutes, _booking_windows(db, session_id)
        )
        if reason:
            raise OperationsError(reason)

        cur = db.execute(
            """
            INSERT INTO bookings (
                request_id, session_id, start_time, end_time, status,
                profile_id, timing_source,
                estimated_duration_minutes, variability_minutes,
                min_planning_minutes, planning_block_minutes, room_turnover_minutes
            ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                session_id,
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
        db.execute("COMMIT")
        return int(cur.lastrowid)
    except Exception:
        db.execute("ROLLBACK")
        raise


def cancel_booking(db: sqlite3.Connection, booking_id: int) -> None:
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute(
            "SELECT id, status FROM bookings WHERE id = ?",
            (booking_id,),
        ).fetchone()
        if row is None:
            raise OperationsError("booking not found")
        reason = can_cancel(row["status"])
        if reason:
            raise OperationsError(reason)
        db.execute(
            "UPDATE bookings SET status = 'cancelled' WHERE id = ?",
            (booking_id,),
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
