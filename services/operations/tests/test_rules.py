from app.rules import (
    BookingWindow,
    SessionWindow,
    booking_conflicts,
    compute_timing_plan,
    session_conflicts,
)
from app.timeutil import intervals_overlap


def test_touching_sessions_do_not_overlap():
    assert intervals_overlap(0, 40, 40, 80) is False
    assert intervals_overlap(0, 41, 40, 80) is True


def test_same_room_is_rejected():
    existing = [SessionWindow(1, "Room A", "Dr. A", "2026-10-10", "09:00", "12:00", 1)]
    candidate = SessionWindow(-1, "room a", "Dr. B", "2026-10-10", "11:00", "13:00", 2)
    assert session_conflicts(candidate, existing) == "room conflict with session 1"


def test_same_clinician_in_another_room_is_rejected():
    existing = [SessionWindow(1, "Room A", "Dr. Vega", "2026-10-10", "09:00", "12:00", 1)]
    candidate = SessionWindow(-1, "Room B", "Dr. Vega", "2026-10-10", "10:00", "11:00", 1)
    assert session_conflicts(candidate, existing) == "clinician conflict with session 1"


def test_different_room_and_clinician_can_overlap():
    existing = [SessionWindow(1, "Room A", "Dr. A", "2026-10-10", "09:00", "12:00", 1)]
    candidate = SessionWindow(-1, "Room B", "Dr. B", "2026-10-10", "10:00", "11:00", 2)
    assert session_conflicts(candidate, existing) is None


def test_end_time_must_be_after_start():
    candidate = SessionWindow(-1, "Room A", "Dr. A", "2026-10-10", "12:00", "09:00", 1)
    assert session_conflicts(candidate, []) == "session end must be after start"


def test_catalogue_durations_stay_30_and_45():
    gastroscopy = compute_timing_plan(
        start_time="09:00",
        estimated_duration_minutes=30,
        variability_minutes=0,
        min_planning_minutes=30,
        room_turnover_minutes=10,
        profile_id=None,
        source="catalogue",
    )
    colonoscopy = compute_timing_plan(
        start_time="09:00",
        estimated_duration_minutes=45,
        variability_minutes=0,
        min_planning_minutes=45,
        room_turnover_minutes=15,
        profile_id=None,
        source="catalogue",
    )
    assert gastroscopy.end_time == "09:30"
    assert gastroscopy.planning_block_minutes == 30
    assert colonoscopy.end_time == "09:45"
    assert colonoscopy.planning_block_minutes == 45


def test_vega_profile_stays_at_the_30_minute_minimum():
    plan = compute_timing_plan(
        start_time="09:00",
        estimated_duration_minutes=25,
        variability_minutes=5,
        min_planning_minutes=30,
        room_turnover_minutes=10,
        profile_id=1,
        source="profile",
    )
    assert plan.planning_block_minutes == 30
    assert plan.occupied_end_time == "09:40"


def test_turnover_blocks_a_following_booking():
    existing = [BookingWindow(1, 4, "09:00", "09:30", "active", 10)]
    assert booking_conflicts("09:30", "10:00", 10, existing) == "overlaps booking 1 (including room turnover)"
    assert booking_conflicts("09:40", "10:10", 10, existing) is None


def test_missing_json_is_rejected():
    from app.main import app

    response = app.test_client().post("/sessions", json={})
    assert response.status_code == 400
    assert "missing field" in response.get_json()["error"]
