"""Scheduling rules copied from the original clinic.

A procedure block is max(centre minimum, estimate + variability).
Room occupation adds the procedure's turnover. Intervals are half-open.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.timeutil import (
    add_minutes_hhmm,
    combine_date_time,
    intervals_overlap,
    labels_match,
    normalize_hhmm,
    parse_datetime_local,
    parse_hhmm,
)


class OperationsError(Exception):
    def __init__(self, reason: str, status: int = 400):
        super().__init__(reason)
        self.reason = reason
        self.status = status


@dataclass(frozen=True)
class SessionWindow:
    id: int
    room_label: str
    clinician_label: str
    session_date: str
    start_time: str
    end_time: str
    clinician_id: int | None = None


def session_conflicts(candidate: SessionWindow, existing: list[SessionWindow]) -> str | None:
    start = parse_hhmm(candidate.start_time)
    end = parse_hhmm(candidate.end_time)
    if start >= end:
        return "session end must be after start"

    for other in existing:
        if other.id == candidate.id or other.session_date != candidate.session_date:
            continue
        if not intervals_overlap(start, end, parse_hhmm(other.start_time), parse_hhmm(other.end_time)):
            continue
        if labels_match(other.room_label, candidate.room_label):
            return f"room conflict with session {other.id}"
        same_clinician = (
            candidate.clinician_id is not None
            and other.clinician_id is not None
            and candidate.clinician_id == other.clinician_id
        ) or labels_match(other.clinician_label, candidate.clinician_label)
        if same_clinician:
            return f"clinician conflict with session {other.id}"
    return None


@dataclass(frozen=True)
class TimingPlan:
    profile_id: int | None
    source: str
    estimated_duration_minutes: int
    variability_minutes: int
    min_planning_minutes: int
    planning_block_minutes: int
    room_turnover_minutes: int
    end_time: str
    occupied_end_time: str


@dataclass(frozen=True)
class BookingWindow:
    id: int
    session_id: int
    start_time: str
    end_time: str
    status: str
    room_turnover_minutes: int = 0


def compute_timing_plan(
    *,
    start_time: str,
    estimated_duration_minutes: int,
    variability_minutes: int,
    min_planning_minutes: int,
    room_turnover_minutes: int,
    profile_id: int | None,
    source: str,
) -> TimingPlan:
    """Same duration math as the original clinic."""
    if estimated_duration_minutes <= 0:
        raise OperationsError("estimated duration must be positive")
    if variability_minutes < 0:
        raise OperationsError("variability cannot be negative")
    if min_planning_minutes <= 0:
        raise OperationsError("centre minimum planning time must be positive")
    if room_turnover_minutes < 0:
        raise OperationsError("room turnover cannot be negative")

    start = normalize_hhmm(start_time)
    planning_block = max(min_planning_minutes, estimated_duration_minutes + variability_minutes)
    end_time = add_minutes_hhmm(start, planning_block)
    occupied_end = add_minutes_hhmm(end_time, room_turnover_minutes)
    return TimingPlan(
        profile_id=profile_id,
        source=source,
        estimated_duration_minutes=estimated_duration_minutes,
        variability_minutes=variability_minutes,
        min_planning_minutes=min_planning_minutes,
        planning_block_minutes=planning_block,
        room_turnover_minutes=room_turnover_minutes,
        end_time=end_time,
        occupied_end_time=occupied_end,
    )


def booking_fits_session(session: SessionWindow, start_time: str, end_time: str, room_turnover_minutes: int) -> str | None:
    start = parse_hhmm(start_time)
    end = parse_hhmm(end_time)
    if start >= end:
        return "booking end must be after start"
    occupied_end = end + room_turnover_minutes
    if start < parse_hhmm(session.start_time) or occupied_end > parse_hhmm(session.end_time):
        return "booking with room turnover does not fit inside the staffed session"
    return None


def booking_conflicts(
    start_time: str,
    end_time: str,
    room_turnover_minutes: int,
    existing: list[BookingWindow],
) -> str | None:
    start = parse_hhmm(start_time)
    occupied_end = parse_hhmm(end_time) + room_turnover_minutes
    for other in existing:
        if other.status not in ("active", "completed", "completion_pending"):
            continue
        other_start = parse_hhmm(other.start_time)
        other_end = parse_hhmm(other.end_time) + other.room_turnover_minutes
        if intervals_overlap(start, occupied_end, other_start, other_end):
            return f"overlaps booking {other.id} (including room turnover)"
    return None


def eligibility_issues(
    *,
    ready: bool,
    available_from: str,
    available_to: str,
    minimum_notice_minutes: int,
    session_date: str,
    start_time: str,
    end_time: str,
    now: datetime,
) -> list[str]:
    """Same waiting-list checks as the original clinic, for one new request."""
    issues: list[str] = []
    if not ready:
        issues.append("not_ready")
    slot_start = combine_date_time(session_date, start_time)
    slot_end = combine_date_time(session_date, end_time)
    avail_from = parse_datetime_local(available_from)
    avail_to = parse_datetime_local(available_to)
    if avail_from >= avail_to:
        issues.append("invalid_availability_window")
    if slot_start < avail_from or slot_end > avail_to:
        issues.append("outside_availability")
    notice = (slot_start - now).total_seconds() / 60.0
    if notice < minimum_notice_minutes:
        issues.append("insufficient_notice")
    return issues
