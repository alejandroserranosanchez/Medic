"""Application service: the only place Operations and Finance meet.

Explain this in the viva:
- Operations marks the booking completed.
- Finance inserts one receivable with a frozen fee snapshot.
- Both writes share one BEGIN IMMEDIATE … COMMIT (or ROLLBACK).
- Finance code never imports operations modules; we pass plain values across.
"""

from __future__ import annotations

import sqlite3

from clinic.finance import repository as finance_repo
from clinic.finance.repository import FinanceError
from clinic.operations.service import OperationsError


def complete_booking(
    db: sqlite3.Connection,
    *,
    booking_id: int,
    performed_date: str,
    due_date: str,
) -> int:
    """Complete an active booking and create exactly one receivable.

    Returns receivable id. Re-running after success returns the existing receivable
    without creating a second economic event.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        booking = db.execute(
            """
            SELECT b.id, b.status, b.request_id, r.procedure_code
            FROM bookings b
            JOIN requests r ON r.id = b.request_id
            WHERE b.id = ?
            """,
            (booking_id,),
        ).fetchone()
        if booking is None:
            raise OperationsError("booking not found")

        existing = db.execute(
            "SELECT id FROM receivables WHERE source_booking_id = ?",
            (booking_id,),
        ).fetchone()

        if booking["status"] == "completed":
            if existing is None:
                raise FinanceError("completed booking is missing its receivable")
            db.execute("COMMIT")
            return int(existing["id"])

        if booking["status"] != "active":
            raise OperationsError(
                f"only active bookings can be completed (status={booking['status']})"
            )
        if existing is not None:
            raise FinanceError("receivable already exists for a non-completed booking")

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
    except Exception:
        db.execute("ROLLBACK")
        raise
