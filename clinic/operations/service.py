"""Operations rules you can explain on paper.

Key ideas:
1) Planning block = max(centre minimum, estimate + variability) from clinician profile or catalogue.
2) Room occupation = planning block + room turnover (saved on the booking).
3) Intervals are half-open [start, end).
4) ready = human scheduling confirmation, not automatic medical clearance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from clinic.timeutil import (
    add_minutes_hhmm,
    combine_date_time,
    intervals_overlap,
    labels_match,
    normalize_hhmm,
    parse_datetime_local,
    parse_hhmm,
)


@dataclass(frozen=True)
class SessionWindow:
    id: int
    room_label: str
    clinician_label: str
    session_date: str
    start_time: str
    end_time: str
    clinician_id: int | None = None


@dataclass(frozen=True)
class BookingWindow:
    id: int
    session_id: int
    start_time: str
    end_time: str
    status: str
    room_turnover_minutes: int = 0


@dataclass(frozen=True)
class TimingPlan:
    """Everything we need to store on a booking so later catalogue edits cannot rewrite history."""

    profile_id: int | None
    source: str  # 'profile' or 'catalogue'
    estimated_duration_minutes: int
    variability_minutes: int
    min_planning_minutes: int
    planning_block_minutes: int
    room_turnover_minutes: int
    end_time: str
    occupied_end_time: str


class OperationsError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


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
    """Deterministic duration math from guide §6.5."""
    if estimated_duration_minutes <= 0:
        raise OperationsError("estimated duration must be positive")
    if variability_minutes < 0:
        raise OperationsError("variability cannot be negative")
    if min_planning_minutes <= 0:
        raise OperationsError("centre minimum planning time must be positive")
    if room_turnover_minutes < 0:
        raise OperationsError("room turnover cannot be negative")

    start = normalize_hhmm(start_time)
    planning_block = max(
        min_planning_minutes,
        estimated_duration_minutes + variability_minutes,
    )
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


def session_conflicts(
    candidate: SessionWindow,
    existing: list[SessionWindow],
) -> str | None:
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
        if labels_match(other.room_label, candidate.room_label):
            return f"room conflict with session {other.id}"
        same_clinician = False
        if (
            candidate.clinician_id is not None
            and other.clinician_id is not None
            and candidate.clinician_id == other.clinician_id
        ):
            same_clinician = True
        elif labels_match(other.clinician_label, candidate.clinician_label):
            same_clinician = True
        if same_clinician:
            return f"clinician conflict with session {other.id}"
    return None


def occupied_end_minutes(end_time: str, room_turnover_minutes: int) -> int:
    return parse_hhmm(end_time) + room_turnover_minutes


def booking_fits_session(
    session: SessionWindow,
    start_time: str,
    end_time: str,
    room_turnover_minutes: int,
) -> str | None:
    start = parse_hhmm(start_time)
    end = parse_hhmm(end_time)
    if start >= end:
        return "booking end must be after start"
    session_start = parse_hhmm(session.start_time)
    session_end = parse_hhmm(session.end_time)
    occupied_end = occupied_end_minutes(end_time, room_turnover_minutes)
    if start < session_start or occupied_end > session_end:
        return "booking with room turnover does not fit inside the staffed session"
    return None


def booking_conflicts(
    start_time: str,
    end_time: str,
    room_turnover_minutes: int,
    existing: list[BookingWindow],
    ignore_booking_id: int | None = None,
) -> str | None:
    start = parse_hhmm(start_time)
    occupied_end = occupied_end_minutes(end_time, room_turnover_minutes)
    for other in existing:
        if ignore_booking_id is not None and other.id == ignore_booking_id:
            continue
        if other.status not in ("active", "completed"):
            continue
        other_start = parse_hhmm(other.start_time)
        other_end = occupied_end_minutes(other.end_time, other.room_turnover_minutes)
        if intervals_overlap(start, occupied_end, other_start, other_end):
            return f"overlaps booking {other.id} (including room turnover)"
    return None


def can_cancel(status: str) -> str | None:
    if status != "active":
        return f"only active bookings can be cancelled (status={status})"
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
    has_active_booking: bool,
    has_completed_booking: bool,
) -> list[str]:
    """Shared checks for manual booking (and later recovery acceptance)."""
    issues: list[str] = []
    if has_completed_booking:
        issues.append("already_completed")
    if has_active_booking:
        issues.append("already_booked")
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
