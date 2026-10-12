"""HTTP routes for capacity / operations screens."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from clinic.clock import now as clock_now
from clinic.db import get_db
from clinic.operations import repository as ops_repo
from clinic.operations.service import OperationsError
from clinic.timeutil import add_minutes_hhmm, combine_date_time, format_hhmm, parse_hhmm

bp = Blueprint("operations", __name__)


def with_timeline(schedule: list[dict], now: datetime) -> list[dict]:
    """Add bar positions, free minutes and per-booking completion info for the templates."""
    for item in schedule:
        s = item["session"]
        start = parse_hhmm(s["start_time"])
        length = parse_hhmm(s["end_time"]) - start
        session_day = date.fromisoformat(s["session_date"])
        item["free_minutes"] = sum(parse_hhmm(b) - parse_hhmm(a) for a, b in item["gaps"])
        item["past"] = session_day < now.date()
        item["completable"] = {
            b["id"]: now >= combine_date_time(s["session_date"], b["start_time"])
            for b in item["bookings"]
        }
        item["due_date"] = (session_day + timedelta(days=14)).isoformat()

        def pct(hhmm: str) -> float:
            return round(100 * (parse_hhmm(hhmm) - start) / length, 2)

        item["blocks"] = []
        for b in item["bookings"]:
            if b["status"] == "cancelled":
                continue
            room_free = add_minutes_hhmm(b["end_time"], int(b["room_turnover_minutes"] or 0))
            item["blocks"].append(
                {
                    "booking": b,
                    "room_free": room_free,
                    "left": pct(b["start_time"]),
                    "width": pct(b["end_time"]) - pct(b["start_time"]),
                    "turnover_width": pct(room_free) - pct(b["end_time"]),
                }
            )
        item["gap_blocks"] = [
            {"start": g_start, "end": g_end, "left": pct(g_start), "width": pct(g_end) - pct(g_start)}
            for g_start, g_end in item["gaps"]
        ]
        first_hour = -(-start // 60) * 60
        item["ticks"] = [
            {"label": format_hhmm(m), "left": pct(format_hhmm(m))}
            for m in range(first_hour, start + length + 1, 60)
        ]
    return schedule


@bp.get("/capacity")
def capacity():
    db = get_db()
    now = clock_now()
    today = now.date()
    schedule = with_timeline(ops_repo.list_schedule(db), now)

    slot = None
    session_id = request.args.get("session", type=int)
    start = request.args.get("start")
    if session_id and start:
        try:
            slot = {
                "session": next(
                    (i["session"] for i in schedule if i["session"]["id"] == session_id), None
                ),
                "start_time": start,
                "candidates": ops_repo.slot_candidates(db, session_id=session_id, start_time=start),
            }
        except (OperationsError, ValueError) as exc:
            flash(str(getattr(exc, "reason", exc)), "error")

    procedures = ops_repo.list_procedure_types(db)
    return render_template(
        "capacity.html",
        schedule=schedule,
        slot=slot,
        waiting=ops_repo.list_waiting_requests(db),
        procedures=procedures,
        procedure_names={p["code"]: p["display_name"] for p in procedures},
        clinicians=ops_repo.list_clinicians(db),
        tomorrow=(today + timedelta(days=1)).isoformat(),
    )


@bp.post("/capacity/sessions")
def add_session():
    db = get_db()
    try:
        ops_repo.create_session(
            db,
            room_label=request.form["room_label"],
            clinician_id=int(request.form["clinician_id"]),
            session_date=request.form["session_date"],
            start_time=request.form["start_time"],
            end_time=request.form["end_time"],
        )
        flash("Session added to the schedule.", "ok")
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
            requested_at=request.form.get("requested_at")
            or clock_now().isoformat(timespec="seconds"),
            ready=request.form.get("ready") == "on",
            available_from=request.form["available_from"],
            available_to=request.form["available_to"],
            minimum_notice_minutes=int(request.form["minimum_notice_minutes"]),
        )
        flash("Patient added to the waiting list.", "ok")
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
        )
        flash("Patient booked. The end time was calculated from the clinician's profile.", "ok")
    except (OperationsError, KeyError, ValueError) as exc:
        flash(str(getattr(exc, "reason", exc)), "error")
    return redirect(url_for("operations.capacity"))


@bp.post("/capacity/bookings/<int:booking_id>/cancel")
def cancel_booking(booking_id: int):
    db = get_db()
    booking = ops_repo.get_booking(db, booking_id)
    try:
        ops_repo.cancel_booking(db, booking_id)
    except OperationsError as exc:
        flash(exc.reason, "error")
        return redirect(url_for("operations.capacity"))
    flash("Booking cancelled. The slot is free again — see who could take it.", "ok")
    return redirect(
        url_for(
            "operations.capacity",
            session=booking["session_id"],
            start=booking["start_time"],
            _anchor="match",
        )
    )
