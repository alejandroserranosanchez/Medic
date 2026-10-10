"""Payments + investment screen routes."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from clinic.application import complete_booking
from clinic.clock import now as clock_now
from clinic.db import get_db
from clinic.finance import repository as finance_repo
from clinic.finance.investment import (
    InvestmentError,
    OptionInputs,
    ScenarioInputs,
    compare_scenario,
    example_guide_inputs,
)
from clinic.finance.moneyparse import cents_to_euros, euros_to_cents
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
        cents = euros_to_cents(request.form["amount_eur"])
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


def _option_from_form(prefix: str) -> OptionInputs:
    form = request.form
    return OptionInputs(
        staffed_capacity=int(form[f"{prefix}_staff"]),
        room_capacity=int(form[f"{prefix}_room"]),
        equipment_capacity=int(form[f"{prefix}_equipment"]),
        additional_monthly_staff_cost_cents=euros_to_cents(form[f"{prefix}_extra_staff_eur"]),
        monthly_equipment_cash_cost_cents=euros_to_cents(form[f"{prefix}_monthly_equip_eur"]),
        upfront_equipment_cash_cost_cents=euros_to_cents(form[f"{prefix}_upfront_eur"]),
    )


def _inputs_from_form() -> ScenarioInputs:
    return ScenarioInputs(
        name=request.form["name"],
        procedure_code=request.form["procedure_code"],
        months=int(request.form["months"]),
        monthly_demand=int(request.form["monthly_demand"]),
        expected_receipt_cents=euros_to_cents(request.form["expected_receipt_eur"]),
        variable_cost_cents=euros_to_cents(request.form["variable_cost_eur"]),
        keep=_option_from_form("keep"),
        buy=_option_from_form("buy"),
        lease=_option_from_form("lease"),
    )


@bp.get("/investment")
def investment():
    db = get_db()
    example = example_guide_inputs()
    preview = compare_scenario(example)
    saved = finance_repo.list_investment_scenarios(db)
    selected_id = request.args.get("id", type=int)
    selected = None
    if selected_id is not None:
        try:
            selected = finance_repo.get_investment_scenario(db, selected_id)
        except FinanceError as exc:
            flash(exc.reason, "error")
    return render_template(
        "investment.html",
        example=example,
        preview=preview,
        saved=saved,
        selected=selected,
        cents_to_euros=cents_to_euros,
    )


@bp.post("/investment/save")
def investment_save():
    db = get_db()
    try:
        inputs = _inputs_from_form()
        scenario_id = finance_repo.save_investment_scenario(
            db,
            inputs=inputs,
            created_at=clock_now().isoformat(sep="T"),
        )
        flash(f"Scenario #{scenario_id} saved with frozen input/output snapshots.", "ok")
        return redirect(url_for("finance.investment", id=scenario_id))
    except (InvestmentError, FinanceError, ValueError, KeyError) as exc:
        flash(str(getattr(exc, "reason", exc)), "error")
        return redirect(url_for("finance.investment"))
