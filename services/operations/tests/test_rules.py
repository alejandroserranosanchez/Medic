from app.rules import SessionWindow, session_conflicts
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


def test_missing_json_is_rejected():
    from app.main import app

    response = app.test_client().post("/sessions", json={})
    assert response.status_code == 400
    assert "missing field" in response.get_json()["error"]
