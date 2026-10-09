"""Defendable tests for profiles, derived duration, eligibility and snapshots."""

from __future__ import annotations

from datetime import datetime

import pytest

from clinic.db import get_db
from clinic.operations import repository as ops_repo
from clinic.operations.service import OperationsError, compute_timing_plan


def test_vega_profile_block_is_30_not_raw_estimate():
    # estimate 25 + variability 5 = 30; centre min 30 → block 30
    plan = compute_timing_plan(
        start_time="10:00",
        estimated_duration_minutes=25,
        variability_minutes=5,
        min_planning_minutes=30,
        room_turnover_minutes=10,
        profile_id=1,
        source="profile",
    )
    assert plan.planning_block_minutes == 30
    assert plan.end_time == "10:30"
    assert plan.occupied_end_time == "10:40"


def test_nadal_profile_needs_40_minutes():
    plan = compute_timing_plan(
        start_time="10:00",
        estimated_duration_minutes=35,
        variability_minutes=5,
        min_planning_minutes=30,
        room_turnover_minutes=10,
        profile_id=2,
        source="profile",
    )
    assert plan.planning_block_minutes == 40
    assert plan.end_time == "10:40"
    assert plan.occupied_end_time == "10:50"


def test_centre_minimum_wins_over_short_estimate():
    plan = compute_timing_plan(
        start_time="09:00",
        estimated_duration_minutes=20,
        variability_minutes=0,
        min_planning_minutes=30,
        room_turnover_minutes=10,
        profile_id=None,
        source="catalogue",
    )
    assert plan.planning_block_minutes == 30


def test_booking_uses_session_clinician_profile(app):
    with app.app_context():
        db = get_db()
        # Cancel seed booking so the morning is free.
        active = next(b for b in ops_repo.list_bookings(db) if b["status"] == "active")
        ops_repo.cancel_booking(db, active["id"])

        clinicians = {c["display_name"]: c["id"] for c in ops_repo.list_clinicians(db)}
        nadal_session = ops_repo.create_session(
            db,
            room_label="Room B",
            clinician_id=clinicians["Dr. Nadal"],
            session_date="2026-10-10",
            start_time="09:00",
            end_time="12:00",
        )
        request_id = ops_repo.create_request(
            db,
            patient_ref="P-NADAL",
            procedure_code="GASTRO",
            priority=1,
            requested_at="2026-10-09T10:00:00",
            ready=True,
            available_from="2026-10-10T09:00:00",
            available_to="2026-10-10T18:00:00",
            minimum_notice_minutes=0,
        )
        booking_id = ops_repo.create_booking(
            db,
            request_id=request_id,
            session_id=nadal_session,
            start_time="10:00",
            now=datetime(2026, 10, 9, 12, 0, 0),
        )
        row = db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        assert row["end_time"] == "10:40"
        assert row["planning_block_minutes"] == 40
        assert row["timing_source"] == "profile"
        assert row["estimated_duration_minutes"] == 35
        assert row["variability_minutes"] == 5


def test_reject_not_ready(app):
    with app.app_context():
        db = get_db()
        session_id = ops_repo.list_sessions(db)[0]["id"]
        request_id = ops_repo.create_request(
            db,
            patient_ref="P-NOTREADY",
            procedure_code="GASTRO",
            priority=1,
            requested_at="2026-10-09T10:00:00",
            ready=False,
            available_from="2026-10-10T09:00:00",
            available_to="2026-10-10T18:00:00",
            minimum_notice_minutes=0,
        )
        with pytest.raises(OperationsError, match="not_ready"):
            ops_repo.create_booking(
                db,
                request_id=request_id,
                session_id=session_id,
                start_time="11:00",
                now=datetime(2026, 10, 9, 12, 0, 0),
            )


def test_reject_insufficient_notice(app):
    with app.app_context():
        db = get_db()
        session_id = ops_repo.list_sessions(db)[0]["id"]
        request_id = ops_repo.create_request(
            db,
            patient_ref="P-NOTICE",
            procedure_code="GASTRO",
            priority=1,
            requested_at="2026-10-09T10:00:00",
            ready=True,
            available_from="2026-10-10T09:00:00",
            available_to="2026-10-10T18:00:00",
            minimum_notice_minutes=24 * 60,
        )
        with pytest.raises(OperationsError, match="insufficient_notice"):
            ops_repo.create_booking(
                db,
                request_id=request_id,
                session_id=session_id,
                start_time="11:00",
                now=datetime(2026, 10, 9, 12, 0, 0),
            )


def test_invalid_date_rejected(app):
    with app.app_context():
        db = get_db()
        clinicians = ops_repo.list_clinicians(db)
        with pytest.raises(ValueError):
            ops_repo.create_session(
                db,
                room_label="Room Z",
                clinician_id=clinicians[0]["id"],
                session_date="nonsense",
                start_time="09:00",
                end_time="12:00",
            )


def test_negative_notice_rejected(app):
    with app.app_context():
        db = get_db()
        with pytest.raises(OperationsError, match="minimum notice"):
            ops_repo.create_request(
                db,
                patient_ref="P-NEG",
                procedure_code="GASTRO",
                priority=1,
                requested_at="2026-10-09T10:00:00",
                ready=True,
                available_from="2026-10-10T09:00:00",
                available_to="2026-10-10T18:00:00",
                minimum_notice_minutes=-1,
            )


def test_editing_profile_does_not_change_existing_booking(app):
    with app.app_context():
        db = get_db()
        booking = next(b for b in ops_repo.list_bookings(db) if b["status"] == "active")
        old_block = booking["planning_block_minutes"]
        db.execute(
            "UPDATE clinician_procedure_profiles SET estimated_duration_minutes = 90 WHERE id = ?",
            (booking["profile_id"],),
        )
        # No commit wrapper needed beyond statement in autocommit mode; re-read booking.
        refreshed = db.execute(
            "SELECT planning_block_minutes, estimated_duration_minutes FROM bookings WHERE id = ?",
            (booking["id"],),
        ).fetchone()
        assert refreshed["planning_block_minutes"] == old_block
        assert refreshed["estimated_duration_minutes"] == booking["estimated_duration_minutes"]
