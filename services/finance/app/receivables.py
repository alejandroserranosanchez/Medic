"""Finance rows and money status. This module never opens the Operations database."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pymssql

from app.timeutil import normalize_label, validate_iso_date


class FinanceError(Exception):
    def __init__(self, reason: str, status: int = 400):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def classify_balance(
    *,
    expected_fee_cents: int,
    paid_cents: int,
    due_date: str,
    as_of_date: str,
) -> dict:
    """Same labels as the original clinic: unpaid, partial, settled, overpaid."""
    if expected_fee_cents < 0 or paid_cents < 0:
        raise FinanceError("money amounts cannot be negative")
    balance = expected_fee_cents - paid_cents
    if paid_cents == 0 and expected_fee_cents > 0:
        status = "unpaid"
    elif paid_cents > expected_fee_cents:
        status = "overpaid"
    elif paid_cents == expected_fee_cents:
        status = "settled"
    else:
        status = "partial"
    return {
        "expected_fee_cents": expected_fee_cents,
        "paid_cents": paid_cents,
        "balance_cents": balance,
        "status": status,
        "overdue": balance > 0 and as_of_date > due_date,
    }


def _integer(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FinanceError(f"{name} must be an integer")
    if value > 2_147_483_647:
        raise FinanceError(f"{name} is out of range")
    return value


def _procedure_code(value) -> str:
    if not isinstance(value, str):
        raise FinanceError("procedure code must be text")
    try:
        code = normalize_label(value).upper()
    except ValueError as exc:
        raise FinanceError("procedure code is required") from exc
    if len(code) > 20:
        raise FinanceError("procedure code is too long")
    return code


def _reference(value) -> str:
    if not isinstance(value, str):
        raise FinanceError("payment reference must be text")
    reference = " ".join(value.split())
    if not reference:
        raise FinanceError("payment reference required")
    if len(reference) > 200:
        raise FinanceError("payment reference is too long")
    return reference


def _date_text(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()[:10]


def _receivable_row(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "source_booking_id": int(row["source_booking_id"]),
        "procedure_code": str(row["procedure_code"]).strip(),
        "performed_date": _date_text(row["performed_date"]),
        "due_date": _date_text(row["due_date"]),
        "expected_fee_cents": int(row["expected_fee_cents"]),
    }


def _payment_row(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "receivable_id": int(row["receivable_id"]),
        "payment_reference": str(row["payment_reference"]).strip(),
        "amount_cents": int(row["amount_cents"]),
        "paid_date": _date_text(row["paid_date"]),
    }


_RECEIVABLE = """
SELECT id, source_booking_id, procedure_code,
       CONVERT(char(10), performed_date, 23) AS performed_date,
       CONVERT(char(10), due_date, 23) AS due_date,
       expected_fee_cents
FROM dbo.receivables
"""

_PAYMENT = """
SELECT id, receivable_id, payment_reference, amount_cents,
       CONVERT(char(10), paid_date, 23) AS paid_date
FROM dbo.payments
"""


def create_receivable(
    conn,
    *,
    source_booking_id: int,
    procedure_code: str,
    performed_date: str,
    due_date: str,
    expected_fee_cents: int,
) -> dict:
    booking_id = _integer(source_booking_id, "source_booking_id")
    if booking_id < 1:
        raise FinanceError("source_booking_id must be a positive integer")
    code = _procedure_code(procedure_code)
    performed = validate_iso_date(performed_date)
    due = validate_iso_date(due_date)
    if due < performed:
        raise FinanceError("due date cannot be before the performed date")
    fee = _integer(expected_fee_cents, "expected_fee_cents")
    if fee < 0:
        raise FinanceError("expected_fee_cents cannot be negative")
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute(
            """
            SELECT id FROM dbo.receivables WITH (UPDLOCK, HOLDLOCK)
            WHERE source_booking_id = %s
            """,
            (booking_id,),
        )
        if cursor.fetchone() is not None:
            raise FinanceError("receivable already exists for this booking", status=409)
        cursor.execute(
            """
            INSERT INTO dbo.receivables (
                source_booking_id, procedure_code, performed_date, due_date, expected_fee_cents
            )
            OUTPUT INSERTED.id
            VALUES (%s, %s, %s, %s, %s)
            """,
            (booking_id, code, performed, due, fee),
        )
        receivable_id = int(cursor.fetchone()["id"])
        conn.commit()
    except FinanceError:
        conn.rollback()
        raise
    except pymssql.IntegrityError as exc:
        conn.rollback()
        if "CK_" in str(exc):
            raise FinanceError("the database rejected this money record") from exc
        raise FinanceError("receivable already exists for this booking", status=409) from exc
    except Exception:
        conn.rollback()
        raise
    return get_receivable(conn, receivable_id)


def get_receivable(conn, receivable_id: int) -> dict:
    cursor = conn.cursor(as_dict=True)
    cursor.execute(_RECEIVABLE + " WHERE id = %s", (receivable_id,))
    row = cursor.fetchone()
    if row is None:
        raise FinanceError("receivable not found", status=404)
    return _receivable_row(row)


def record_payment(
    conn,
    *,
    receivable_id: int,
    payment_reference: str,
    amount_cents: int,
    paid_date: str,
) -> tuple[dict, bool]:
    """Return the payment and whether this call inserted it."""
    reference = _reference(payment_reference)
    amount = _integer(amount_cents, "amount_cents")
    if amount <= 0:
        raise FinanceError("payment amount must be positive cents")
    paid = validate_iso_date(paid_date)
    cursor = conn.cursor(as_dict=True)
    try:
        cursor.execute(
            "SELECT id FROM dbo.receivables WITH (UPDLOCK, HOLDLOCK) WHERE id = %s",
            (receivable_id,),
        )
        if cursor.fetchone() is None:
            raise FinanceError("receivable not found", status=404)
        cursor.execute(
            """
            SELECT id, receivable_id, payment_reference, amount_cents,
                   CONVERT(char(10), paid_date, 23) AS paid_date
            FROM dbo.payments WITH (UPDLOCK, HOLDLOCK)
            WHERE payment_reference = %s
            """,
            (reference,),
        )
        existing = cursor.fetchone()
        if existing is not None:
            same = (
                int(existing["receivable_id"]) == receivable_id
                and int(existing["amount_cents"]) == amount
                and _date_text(existing["paid_date"]) == paid
            )
            if not same:
                raise FinanceError(
                    "payment reference already used with different details",
                    status=409,
                )
            conn.commit()
            return _payment_row(existing), False
        cursor.execute(
            """
            INSERT INTO dbo.payments (
                receivable_id, payment_reference, amount_cents, paid_date
            )
            OUTPUT INSERTED.id, INSERTED.receivable_id, INSERTED.payment_reference,
                   INSERTED.amount_cents, INSERTED.paid_date
            VALUES (%s, %s, %s, %s)
            """,
            (receivable_id, reference, amount, paid),
        )
        created = _payment_row(cursor.fetchone())
        conn.commit()
        return created, True
    except FinanceError:
        conn.rollback()
        raise
    except pymssql.IntegrityError as exc:
        conn.rollback()
        raise FinanceError(
            "payment reference already used with different details",
            status=409,
        ) from exc
    except Exception:
        conn.rollback()
        raise


def get_balance(conn, receivable_id: int, as_of_date: str | None = None) -> dict:
    as_of = validate_iso_date(as_of_date) if as_of_date else datetime.now(timezone.utc).date().isoformat()
    receivable = get_receivable(conn, receivable_id)
    cursor = conn.cursor(as_dict=True)
    cursor.execute(
        _PAYMENT + " WHERE receivable_id = %s ORDER BY paid_date, id",
        (receivable_id,),
    )
    payments = [_payment_row(row) for row in cursor.fetchall()]
    paid = sum(item["amount_cents"] for item in payments)
    view = classify_balance(
        expected_fee_cents=receivable["expected_fee_cents"],
        paid_cents=paid,
        due_date=receivable["due_date"],
        as_of_date=as_of,
    )
    return {"receivable_id": receivable["id"], "as_of": as_of, "payments": payments, **view}
