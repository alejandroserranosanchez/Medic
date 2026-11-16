"""Time helpers used by the Operations service.

Copied for this service because its Docker image does not contain the old clinic package.
Canonical clock times are HH:MM.
"""

from __future__ import annotations

import re
from datetime import date

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_hhmm(value: str) -> int:
    text = value.strip()
    match = _TIME_RE.match(text)
    if not match:
        raise ValueError(f"invalid time: {value!r} (use HH:MM)")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid time: {value!r}")
    return hour * 60 + minute


def format_hhmm(minutes: int) -> str:
    if minutes < 0 or minutes >= 24 * 60:
        raise ValueError(f"minutes out of day range: {minutes}")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def normalize_hhmm(value: str) -> str:
    return format_hhmm(parse_hhmm(value))


def intervals_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    """Half-open overlap: [start, end). Touching endpoints do not conflict."""
    return start_a < end_b and start_b < end_a


def validate_iso_date(value: str) -> str:
    text = value.strip()
    if not _DATE_RE.match(text):
        raise ValueError(f"invalid date: {value!r} (use YYYY-MM-DD)")
    date.fromisoformat(text)
    return text


def normalize_label(value: str) -> str:
    text = " ".join(str(value).split())
    if not text:
        raise ValueError("name/label cannot be empty")
    return text


def labels_match(a: str, b: str) -> bool:
    return normalize_label(a).casefold() == normalize_label(b).casefold()
