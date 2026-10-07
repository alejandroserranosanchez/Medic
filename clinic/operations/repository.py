"""SQLite access for the operations domain only."""

from __future__ import annotations

import sqlite3

from clinic.operations.service import (
    BookingWindow,
    OperationsError,
    SessionWindow,
    booking_conflicts,
    booking_fits_session,
    can_cancel,
    session_conflicts,
)


def list_sessions(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        """
        SELECT id, room_label, clinician_label, session_date, start_time, end_time
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
            r.patient_ref,
            r.procedure_code,
            p.turnover_minutes,
            s.room_label,
            s.clinician_label,
            s.session_date
        FROM bookings b
        JOIN requests r ON r.id = b.request_id
        JOIN procedure_types p ON p.code = r.procedure_code
        JOIN sessions s ON s.id = b.session_id
        ORDER BY s.session_date, b.start_time, b.id
        """
    ).fetchall()


def list_requests(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        """
        SELECT id, patient_ref, procedure_code, priority, ready, requested_at
        FROM requests
        ORDER BY priority DESC, requested_at ASC, id ASC
        """
    ).fetchall()


def list_procedure_types(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT code, display_name, duration_minutes, turnover_minutes FROM procedure_types ORDER BY code"
    ).fetchall()


def _session_windows(db: sqlite3.Connection) -> list[SessionWindow]:
    rows = list_sessions(db)
    return [
        SessionWindow(
            id=row["id"],
            room_label=row["room_label"],
            clinician_label=row["clinician_label"],
            session_date=row["session_date"],
            start_time=row["start_time"],
            end_time=row["end_time"],
        )
        for row in rows
    ]


def create_session(
    db: sqlite3.Connection,
    *,
    room_label: str,
    clinician_label: str,
    session_date: str,
    start_time: str,
    end_time: str,
) -> int:
    candidate = SessionWindow(
        id=-1,
        room_label=room_label.strip(),
        clinician_label=clinician_label.strip(),
        session_date=session_date.strip(),
        start_time=start_time.strip(),
        end_time=end_time.strip(),
    )
    reason = session_conflicts(candidate, _session_windows(db))
    if reason:
        raise OperationsError(reason)

    cur = db.execute(
        """
        INSERT INTO sessions (room_label, clinician_label, session_date, start_time, end_time)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            candidate.room_label,
            candidate.clinician_label,
            candidate.session_date,
            candidate.start_time,
            candidate.end_time,
        ),
    )
    db.commit()
    return int(cur.lastrowid)


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
    exists = db.execute(
        "SELECT 1 FROM procedure_types WHERE code = ?",
        (procedure_code,),
    ).fetchone()
    if exists is None:
        raise OperationsError(f"unknown procedure code: {procedure_code}")

    cur = db.execute(
        """
        INSERT INTO requests (
            patient_ref, procedure_code, priority, requested_at, ready,
            available_from, available_to, minimum_notice_minutes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            patient_ref.strip(),
            procedure_code,
            int(priority),
            requested_at.strip(),
            1 if ready else 0,
            available_from.strip(),
            available_to.strip(),
            int(minimum_notice_minutes),
        ),
    )
    db.commit()
    return int(cur.lastrowid)


def create_booking(
    db: sqlite3.Connection,
    *,
    request_id: int,
    session_id: int,
    start_time: str,
    end_time: str,
) -> int:
    request = db.execute(
        """
        SELECT r.id, r.procedure_code, p.turnover_minutes
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
    if active is not None:
        raise OperationsError("request already has an active booking")

    session_row = db.execute(
        """
        SELECT id, room_label, clinician_label, session_date, start_time, end_time
        FROM sessions WHERE id = ?
        """,
        (session_id,),
    ).fetchone()
    if session_row is None:
        raise OperationsError("session not found")

    session = SessionWindow(
        id=session_row["id"],
        room_label=session_row["room_label"],
        clinician_label=session_row["clinician_label"],
        session_date=session_row["session_date"],
        start_time=session_row["start_time"],
        end_time=session_row["end_time"],
    )
    turnover = int(request["turnover_minutes"])
    reason = booking_fits_session(session, start_time, end_time, turnover)
    if reason:
        raise OperationsError(reason)

    existing_rows = db.execute(
        """
        SELECT b.id, b.session_id, b.start_time, b.end_time, b.status, p.turnover_minutes
        FROM bookings b
        JOIN requests r ON r.id = b.request_id
        JOIN procedure_types p ON p.code = r.procedure_code
        WHERE b.session_id = ? AND b.status = 'active'
        """,
        (session_id,),
    ).fetchall()
    existing = [
        BookingWindow(
            id=row["id"],
            session_id=row["session_id"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            status=row["status"],
            turnover_minutes=int(row["turnover_minutes"]),
        )
        for row in existing_rows
    ]
    reason = booking_conflicts(start_time, end_time, turnover, existing)
    if reason:
        raise OperationsError(reason)

    cur = db.execute(
        """
        INSERT INTO bookings (request_id, session_id, start_time, end_time, status)
        VALUES (?, ?, ?, ?, 'active')
        """,
        (request_id, session_id, start_time.strip(), end_time.strip()),
    )
    db.commit()
    return int(cur.lastrowid)


def cancel_booking(db: sqlite3.Connection, booking_id: int) -> None:
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
    db.commit()
