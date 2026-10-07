"""Pure-ish operations rules: session conflicts, booking fit, cancellation.

These functions are what tests should cover first — not Flask routing.
"""

from __future__ import annotations

from dataclasses import dataclass

from clinic.timeutil import intervals_overlap, parse_hhmm


@dataclass(frozen=True)
class SessionWindow:
    id: int
    room_label: str
    clinician_label: str
    session_date: str
    start_time: str
    end_time: str


@dataclass(frozen=True)
class BookingWindow:
    id: int
    session_id: int
    start_time: str
    end_time: str
    status: str
    turnover_minutes: int = 0


class OperationsError(Exception):
    """Domain rule violation with a short reason for UI/tests."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def session_conflicts(
    candidate: SessionWindow,
    existing: list[SessionWindow],
) -> str | None:
    """Reject overlapping sessions that share room or clinician on the same date."""
    c_start = parse_hhmm(candidate.start_time)
    c_end = parse_hhmm(candidate.end_time)
    if c_start >= c_end:
        return "session end must be after start"

    for other in existing:
        if other.id == candidate.id:
            continue
        if other.session_date != candidate.session_date:
            continue
        o_start = parse_hhmm(other.start_time)
        o_end = parse_hhmm(other.end_time)
        if not intervals_overlap(c_start, c_end, o_start, o_end):
            continue
        if other.room_label == candidate.room_label:
            return f"room conflict with session {other.id}"
        if other.clinician_label == candidate.clinician_label:
            return f"clinician conflict with session {other.id}"
    return None


def occupied_end_minutes(end_time: str, turnover_minutes: int) -> int:
    """Occupied interval is [start, end+turnover) in half-open minutes."""
    return parse_hhmm(end_time) + turnover_minutes


def booking_fits_session(
    session: SessionWindow,
    start_time: str,
    end_time: str,
    turnover_minutes: int,
) -> str | None:
    start = parse_hhmm(start_time)
    end = parse_hhmm(end_time)
    if start >= end:
        return "booking end must be after start"
    session_start = parse_hhmm(session.start_time)
    session_end = parse_hhmm(session.end_time)
    occupied_end = occupied_end_minutes(end_time, turnover_minutes)
    if start < session_start or occupied_end > session_end:
        return "booking with turnover does not fit inside the staffed session"
    return None


def booking_conflicts(
    start_time: str,
    end_time: str,
    turnover_minutes: int,
    existing_active: list[BookingWindow],
    ignore_booking_id: int | None = None,
) -> str | None:
    start = parse_hhmm(start_time)
    occupied_end = occupied_end_minutes(end_time, turnover_minutes)
    for other in existing_active:
        if ignore_booking_id is not None and other.id == ignore_booking_id:
            continue
        if other.status != "active":
            continue
        other_start = parse_hhmm(other.start_time)
        other_end = occupied_end_minutes(other.end_time, other.turnover_minutes)
        if intervals_overlap(start, occupied_end, other_start, other_end):
            return f"overlaps active booking {other.id} (including turnover)"
    return None


def can_cancel(status: str) -> str | None:
    if status != "active":
        return f"only active bookings can be cancelled (status={status})"
    return None
