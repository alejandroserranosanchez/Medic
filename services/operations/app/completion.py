"""Mark a booking done only after Finance confirms the receivable.

Operations owns the booking status. Finance owns the receivable.
There is no transaction across the two databases.
"""

from __future__ import annotations

from datetime import datetime

from app.finance_client import FinanceCallError, post_receivable
from app.rules import OperationsError
from app.timeutil import combine_date_time, validate_iso_date


def complete_booking(
    conn,
    *,
    booking_id: int,
    performed_date: str,
    due_date: str,
    now: datetime | None = None,
) -> tuple[int, dict]:
    when = now or datetime.now()
    performed = validate_iso_date(performed_date)
    due = validate_iso_date(due_date)
    if due < performed:
        raise OperationsError("due date cannot be before the performed date")

    cursor = conn.cursor(as_dict=True)
    cursor.execute(
        """
        SELECT bookings.id, bookings.status, bookings.start_time, bookings.finance_receivable_id,
               requests.procedure_code,
               CONVERT(char(10), sessions.session_date, 23) AS session_date
        FROM dbo.bookings AS bookings
        JOIN dbo.requests AS requests ON requests.id = bookings.request_id
        JOIN dbo.sessions AS sessions ON sessions.id = bookings.session_id
        WHERE bookings.id = %s
        """,
        (booking_id,),
    )
    booking = cursor.fetchone()
    if booking is None:
        raise OperationsError("booking not found", status=404)

    status = str(booking["status"]).strip()
    session_date = str(booking["session_date"]).strip()
    start_time = str(booking["start_time"]).strip()
    procedure_code = str(booking["procedure_code"]).strip()
    stored_receivable = booking["finance_receivable_id"]

    if performed != session_date:
        raise OperationsError(f"performed date must be the booking's session date ({session_date})")
    if status == "cancelled":
        raise OperationsError("only active bookings can be completed (status=cancelled)")
    if status == "completed" and stored_receivable is not None:
        return 200, {
            "booking_id": booking_id,
            "status": "completed",
            "receivable_id": int(stored_receivable),
            "procedure_code": procedure_code,
            "performed_date": session_date,
            "outcome": "already_completed",
        }
    if status not in ("active", "completion_pending", "completed"):
        raise OperationsError(f"only active bookings can be completed (status={status})")
    if when < combine_date_time(session_date, start_time):
        raise OperationsError(
            "this booking has not started yet; it can be completed from "
            f"{session_date} {start_time}"
        )

    was_pending = status == "completion_pending"
    _set_status(conn, booking_id, "completion_pending", None)
    try:
        http_status, body = post_receivable(
            {
                "source_booking_id": booking_id,
                "procedure_code": procedure_code,
                "performed_date": performed,
                "due_date": due,
            }
        )
    except FinanceCallError as exc:
        return _lost_reply(conn, booking_id, exc, was_pending)

    if http_status in (200, 201) and isinstance(body.get("id"), int):
        receivable_id = int(body["id"])
        _set_status(conn, booking_id, "completed", receivable_id)
        outcome = "created" if http_status == 201 else "already_recorded"
        return 200, _done(
            booking_id,
            receivable_id,
            procedure_code,
            performed,
            due,
            outcome,
            body.get("expected_fee_cents"),
        )

    if http_status == 409:
        return 409, {
            "error": body.get("error") or "finance already has a different receivable for this booking",
            "booking_status": "completion_pending",
        }
    if http_status == 400 and not was_pending:
        _set_status(conn, booking_id, "active", None)
        return 400, {"error": body.get("error") or "finance rejected the receivable", "booking_status": "active"}
    if http_status == 400:
        return 400, {
            "error": body.get("error") or "finance rejected the receivable",
            "booking_status": "completion_pending",
        }
    return 503, {
        "error": "finance result is unknown; the booking stays completion_pending",
        "booking_status": "completion_pending",
    }


def _lost_reply(conn, booking_id: int, exc: FinanceCallError, was_pending: bool) -> tuple[int, dict]:
    if exc.kind in ("refused", "unconfigured") and not was_pending:
        _set_status(conn, booking_id, "active", None)
        message = (
            "FINANCE_SERVICE_URL is not set"
            if exc.kind == "unconfigured"
            else "finance is not accepting connections"
        )
        return 503, {"error": message, "booking_status": "active"}
    return 503, {
        "error": "finance result is unknown; the booking stays completion_pending",
        "booking_status": "completion_pending",
    }


def _set_status(conn, booking_id: int, status: str, receivable_id: int | None) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE dbo.bookings
        SET status = %s, finance_receivable_id = %s
        WHERE id = %s
        """,
        (status, receivable_id, booking_id),
    )
    conn.commit()


def _done(
    booking_id: int,
    receivable_id: int,
    procedure_code: str,
    performed: str,
    due: str,
    outcome: str,
    fee: int | None = None,
) -> dict:
    body = {
        "booking_id": booking_id,
        "status": "completed",
        "receivable_id": receivable_id,
        "procedure_code": procedure_code,
        "performed_date": performed,
        "due_date": due,
        "outcome": outcome,
    }
    if isinstance(fee, int) and not isinstance(fee, bool):
        body["expected_fee_cents"] = fee
    return body
