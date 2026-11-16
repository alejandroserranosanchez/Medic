"""Session clash rules. Same meaning as the original clinic, without bookings."""

from __future__ import annotations

from dataclasses import dataclass

from app.timeutil import intervals_overlap, labels_match, parse_hhmm


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
