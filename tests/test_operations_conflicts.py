"""Core operations rules: conflicts, turnover fit, cancellation."""

from __future__ import annotations

import pytest

from clinic.db import get_db
from clinic.operations import repository as ops_repo
from clinic.operations.service import (
    BookingWindow,
    OperationsError,
    SessionWindow,
    booking_conflicts,
    booking_fits_session,
    session_conflicts,
)
from clinic.timeutil import intervals_overlap


def test_half_open_touching_intervals_do_not_overlap():
    assert intervals_overlap(0, 40, 40, 80) is False
    assert intervals_overlap(0, 41, 40, 80) is True


def test_room_conflict_rejected():
    existing = [
        SessionWindow(1, "Room A", "Dr. A", "2026-10-10", "09:00", "12:00"),
    ]
    candidate = SessionWindow(-1, "Room A", "Dr. B", "2026-10-10", "11:00", "13:00")
    assert session_conflicts(candidate, existing) == "room conflict with session 1"


def test_clinician_conflict_rejected():
    existing = [
        SessionWindow(1, "Room A", "Dr. Vega", "2026-10-10", "09:00", "12:00"),
    ]
    candidate = SessionWindow(-1, "Room B", "Dr. Vega", "2026-10-10", "10:00", "11:00")
    assert "clinician conflict" in (session_conflicts(candidate, existing) or "")


def test_different_room_and_clinician_can_overlap():
    existing = [
        SessionWindow(1, "Room A", "Dr. A", "2026-10-10", "09:00", "12:00"),
    ]
    candidate = SessionWindow(-1, "Room B", "Dr. B", "2026-10-10", "10:00", "11:00")
    assert session_conflicts(candidate, existing) is None


def test_turnover_prevents_adjacent_booking():
    # First booking 09:00-09:30 with 10m turnover occupies [09:00, 09:40)
    existing = [
        BookingWindow(1, 1, "09:00", "09:30", "active", turnover_minutes=10),
    ]
    reason = booking_conflicts("09:30", "10:00", 10, existing)
    assert reason is not None

    # Exact fit after turnover is allowed: start at 09:40
    assert booking_conflicts("09:40", "10:10", 10, existing) is None


def test_booking_must_fit_session_including_turnover():
    session = SessionWindow(1, "Room A", "Dr. A", "2026-10-10", "09:00", "10:00")
    # 09:30-09:55 + 10 turnover => occupied until 10:05, past session end
    assert booking_fits_session(session, "09:30", "09:55", 10) is not None
    assert booking_fits_session(session, "09:00", "09:30", 10) is None


def test_create_session_persists_conflict_rule(app):
    with app.app_context():
        db = get_db()
        ops_repo.create_session(
            db,
            room_label="Room X",
            clinician_label="Dr. One",
            session_date="2026-10-12",
            start_time="09:00",
            end_time="12:00",
        )
        with pytest.raises(OperationsError, match="room conflict"):
            ops_repo.create_session(
                db,
                room_label="Room X",
                clinician_label="Dr. Two",
                session_date="2026-10-12",
                start_time="11:00",
                end_time="13:00",
            )


def test_cancel_frees_capacity_for_new_booking(app):
    with app.app_context():
        db = get_db()
        # Seed already has session 1 and an active GASTRO booking 09:00-09:30.
        bookings = ops_repo.list_bookings(db)
        active = next(b for b in bookings if b["status"] == "active")
        ops_repo.cancel_booking(db, active["id"])

        request_id = ops_repo.create_request(
            db,
            patient_ref="P-3003",
            procedure_code="GASTRO",
            priority=1,
            requested_at="2026-10-09T12:00:00",
            ready=True,
            available_from="2026-10-10T09:00:00",
            available_to="2026-10-10T18:00:00",
            minimum_notice_minutes=0,
        )
        new_id = ops_repo.create_booking(
            db,
            request_id=request_id,
            session_id=active["session_id"],
            start_time="09:00",
            end_time="09:30",
        )
        assert new_id > 0

        # Cancellation must not create a receivable.
        n = db.execute("SELECT COUNT(*) AS n FROM receivables").fetchone()["n"]
        assert n == 0


def test_duplicate_active_booking_rejected(app):
    with app.app_context():
        db = get_db()
        bookings = ops_repo.list_bookings(db)
        active = next(b for b in bookings if b["status"] == "active")
        with pytest.raises(OperationsError, match="already has an active booking"):
            ops_repo.create_booking(
                db,
                request_id=active["request_id"],
                session_id=active["session_id"],
                start_time="10:00",
                end_time="10:30",
            )
