"""Application service: the only place Operations and Finance meet.

- Operations data: the booking is marked completed.
- Finance data: one receivable is inserted with a frozen fee snapshot.
- Both writes share one BEGIN IMMEDIATE ... COMMIT, or ROLLBACK together.
- Callers (e.g. finance routes) only see CompletionError, so they never import Operations.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from clinic.clock import now as clock_now
from clinic.finance import repository as finance_repo
from clinic.finance.repository import FinanceError
from clinic.timeutil import combine_date_time


class CompletionError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def completed_activity(db: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    """Completed bookings by id, so Collections can show what each amount due is for."""
    rows = db.execute(
        """
        SELECT b.id, b.start_time, b.end_time, r.patient_ref, p.display_name AS procedure_name,
               s.room_label, s.clinician_label, s.session_date
        FROM bookings b
        JOIN requests r ON r.id = b.request_id
        JOIN procedure_types p ON p.code = r.procedure_code
        JOIN sessions s ON s.id = b.session_id
        WHERE b.status = 'completed'
        """
    ).fetchall()
    return {int(row["id"]): row for row in rows}


def complete_booking(
    db: sqlite3.Connection,
    *,
    booking_id: int,
    performed_date: str,
    due_date: str,
    now: datetime | None = None,
) -> int:
    """Complete an active booking and create exactly one receivable.

    Returns receivable id. Re-running after success returns the existing receivable
    without creating a second economic event. A booking can only be completed once
    its start time has passed, and the performed date is its session date.
    """
    when = now or clock_now()
    db.execute("BEGIN IMMEDIATE")
    try:
        booking = db.execute(
            """
            SELECT b.id, b.status, b.request_id, b.start_time, r.procedure_code, s.session_date
            FROM bookings b
            JOIN requests r ON r.id = b.request_id
            JOIN sessions s ON s.id = b.session_id
            WHERE b.id = ?
            """,
            (booking_id,),
        ).fetchone()
        if booking is None:
            raise CompletionError("booking not found")

        existing = db.execute(
            "SELECT id FROM receivables WHERE source_booking_id = ?",
            (booking_id,),
        ).fetchone()

        if booking["status"] == "completed":
            if existing is None:
                raise CompletionError("completed booking is missing its receivable")
            db.execute("COMMIT")
            return int(existing["id"])

        if booking["status"] != "active":
            raise CompletionError(
                f"only active bookings can be completed (status={booking['status']})"
            )
        if existing is not None:
            raise CompletionError("receivable already exists for a non-completed booking")
        if when < combine_date_time(booking["session_date"], booking["start_time"]):
            raise CompletionError(
                "this booking has not started yet; it can be completed from "
                f"{booking['session_date']} {booking['start_time']}"
            )
        if performed_date != booking["session_date"]:
            raise CompletionError(
                f"performed date must be the booking's session date ({booking['session_date']})"
            )
        if due_date < performed_date:
            raise CompletionError("due date cannot be before the performed date")

        fee = finance_repo.get_fee_cents(db, booking["procedure_code"])

        db.execute(
            "UPDATE bookings SET status = 'completed' WHERE id = ?",
            (booking_id,),
        )
        receivable_id = finance_repo.insert_receivable(
            db,
            source_booking_id=booking_id,
            procedure_code=booking["procedure_code"],
            performed_date=performed_date,
            due_date=due_date,
            expected_fee_cents=fee,
        )
        db.execute("COMMIT")
        return receivable_id
    except FinanceError as exc:
        db.execute("ROLLBACK")
        raise CompletionError(exc.reason) from exc
    except Exception:
        db.execute("ROLLBACK")
        raise
