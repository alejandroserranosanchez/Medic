"""Payments screen routes."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from clinic.application import complete_booking
from clinic.clock import now as clock_now
from clinic.db import get_db
from clinic.finance import repository as finance_repo
from clinic.finance.repository import FinanceError
from clinic.operations.service import OperationsError
from clinic.timeutil import validate_iso_date

bp = Blueprint("finance", __name__)


@bp.get("/payments")
def payments():
    db = get_db()
    today = clock_now().date().isoformat()
    return render_template(
        "payments.html",
        receivables=finance_repo.list_receivables(db, as_of_date=today),
        as_of_date=today,
    )


@bp.post("/payments/complete")
@bp.post("/payments/complete/<int:booking_id>")
def complete(booking_id: int | None = None):
    db = get_db()
    try:
        if booking_id is None:
            booking_id = int(request.form["booking_id"])
        performed = validate_iso_date(request.form.get("performed_date", ""))
        due = validate_iso_date(request.form.get("due_date", ""))
        receivable_id = complete_booking(
            db,
            booking_id=booking_id,
            performed_date=performed,
            due_date=due,
        )
        flash(f"Booking completed. Receivable #{receivable_id} created (fee snapshot frozen).", "ok")
    except (OperationsError, FinanceError, ValueError, KeyError) as exc:
        flash(str(getattr(exc, "reason", exc)), "error")
    return redirect(url_for("finance.payments"))


@bp.post("/payments/record")
def record_payment():
    db = get_db()
    try:
        # Form euros like 90.00 → cents; reject more than 2 decimals.
        raw = request.form["amount_eur"].strip().replace(",", ".")
        if raw.count(".") > 1:
            raise ValueError("invalid amount")
        if "." in raw:
            whole, frac = raw.split(".", 1)
            if len(frac) > 2:
                raise ValueError("use at most 2 decimal places")
            frac = (frac + "00")[:2]
            cents = int(whole) * 100 + int(frac)
        else:
            cents = int(raw) * 100

        payment_id = finance_repo.record_payment(
            db,
            receivable_id=int(request.form["receivable_id"]),
            payment_reference=request.form["payment_reference"],
            amount_cents=cents,
            paid_date=validate_iso_date(request.form["paid_date"]),
        )
        flash(f"Payment recorded (id={payment_id}).", "ok")
    except (FinanceError, ValueError, KeyError) as exc:
        flash(str(getattr(exc, "reason", exc)), "error")
    return redirect(url_for("finance.payments"))
