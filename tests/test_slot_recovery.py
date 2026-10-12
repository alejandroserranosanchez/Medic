"""Refilling a freed slot: free gaps, ranked candidates with reasons, cancel -> suggestions."""

from __future__ import annotations

from datetime import datetime

from clinic.db import get_db
from clinic.operations import repository as ops_repo
from clinic.operations.service import free_gaps

NOW = datetime(2026, 10, 9, 12, 0, 0)


def test_free_gaps_between_and_after_bookings():
    gaps = free_gaps("09:00", "12:00", [("09:00", "09:40"), ("10:00", "10:40")])

    assert gaps == [("09:40", "10:00"), ("10:40", "12:00")]


def test_empty_session_is_one_gap():
    assert free_gaps("09:00", "12:00", []) == [("09:00", "12:00")]


def test_candidates_ranked_with_reasons(app):
    with app.app_context():
        db = get_db()
        session_id = next(s for s in ops_repo.list_sessions(db) if s["room_label"] == "Room A")["id"]

        candidates = ops_repo.slot_candidates(db, session_id=session_id, start_time="09:40", now=NOW)

    by_ref = {c["request"]["patient_ref"]: c for c in candidates}
    assert by_ref["P-1002"]["issues"] == []
    assert by_ref["P-1002"]["end_time"] == "10:10"
    assert "not_ready" in by_ref["P-1003"]["issues"]
    assert "outside_availability" in by_ref["P-1004"]["issues"]
    assert "P-1001" not in by_ref  # already booked, so not waiting
    assert candidates[0]["request"]["patient_ref"] == "P-1002"  # eligible first


def test_candidate_that_clashes_is_flagged(app):
    with app.app_context():
        db = get_db()
        session_id = next(s for s in ops_repo.list_sessions(db) if s["room_label"] == "Room A")["id"]

        candidates = ops_repo.slot_candidates(db, session_id=session_id, start_time="09:00", now=NOW)

    by_ref = {c["request"]["patient_ref"]: c for c in candidates}
    assert "overlaps_booking" in by_ref["P-1002"]["issues"]


def test_cancel_redirects_to_replacement_suggestions(app, client):
    with app.app_context():
        booking = next(b for b in ops_repo.list_bookings(get_db()) if b["patient_ref"] == "P-1001")

    resp = client.post(f"/capacity/bookings/{booking['id']}/cancel")
    assert resp.status_code == 302
    assert f"session={booking['session_id']}" in resp.location

    page = client.get(resp.location)
    assert b"Selected start" in page.data
    assert b"Book P-1002" in page.data
    assert b"Preparation not confirmed" in page.data
