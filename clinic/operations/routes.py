"""HTTP routes for capacity / operations screens."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from clinic.db import get_db
from clinic.operations import repository as ops_repo
from clinic.operations.service import OperationsError

bp = Blueprint("operations", __name__)


@bp.get("/capacity")
def capacity():
    db = get_db()
    return render_template(
        "capacity.html",
        sessions=ops_repo.list_sessions(db),
        bookings=ops_repo.list_bookings(db),
        requests=ops_repo.list_requests(db),
        procedures=ops_repo.list_procedure_types(db),
    )


@bp.post("/capacity/sessions")
def add_session():
    db = get_db()
    try:
        ops_repo.create_session(
            db,
            room_label=request.form["room_label"],
            clinician_label=request.form["clinician_label"],
            session_date=request.form["session_date"],
            start_time=request.form["start_time"],
            end_time=request.form["end_time"],
        )
        flash("Session saved.", "ok")
    except (OperationsError, KeyError, ValueError) as exc:
        flash(str(getattr(exc, "reason", exc)), "error")
    return redirect(url_for("operations.capacity"))


@bp.post("/capacity/requests")
def add_request():
    db = get_db()
    try:
        ops_repo.create_request(
            db,
            patient_ref=request.form["patient_ref"],
            procedure_code=request.form["procedure_code"],
            priority=int(request.form["priority"]),
            requested_at=request.form["requested_at"],
            ready=request.form.get("ready") == "on",
            available_from=request.form["available_from"],
            available_to=request.form["available_to"],
            minimum_notice_minutes=int(request.form["minimum_notice_minutes"]),
        )
        flash("Waiting request saved.", "ok")
    except (OperationsError, KeyError, ValueError) as exc:
        flash(str(getattr(exc, "reason", exc)), "error")
    return redirect(url_for("operations.capacity"))


@bp.post("/capacity/bookings")
def add_booking():
    db = get_db()
    try:
        ops_repo.create_booking(
            db,
            request_id=int(request.form["request_id"]),
            session_id=int(request.form["session_id"]),
            start_time=request.form["start_time"],
            end_time=request.form["end_time"],
        )
        flash("Booking created.", "ok")
    except (OperationsError, KeyError, ValueError) as exc:
        flash(str(getattr(exc, "reason", exc)), "error")
    return redirect(url_for("operations.capacity"))


@bp.post("/capacity/bookings/<int:booking_id>/cancel")
def cancel_booking(booking_id: int):
    db = get_db()
    try:
        ops_repo.cancel_booking(db, booking_id)
        flash("Booking cancelled. Capacity is free; no receivable was created.", "ok")
    except OperationsError as exc:
        flash(exc.reason, "error")
    return redirect(url_for("operations.capacity"))
