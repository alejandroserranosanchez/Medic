"""Time helpers. Canonical clock times are always HH:MM (zero-padded)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_hhmm(value: str) -> int:
    """Return minutes from midnight. Accepts H:MM or HH:MM; callers should store normalize_hhmm()."""
    text = value.strip()
    match = _TIME_RE.match(text)
    if not match:
        raise ValueError(f"invalid time: {value!r} (use HH:MM)")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid time: {value!r}")
    return hour * 60 + minute


def normalize_hhmm(value: str) -> str:
    """Canonical HH:MM so SQLite text CHECKs and comparisons stay consistent."""
    return format_hhmm(parse_hhmm(value))


def format_hhmm(minutes: int) -> str:
    if minutes < 0 or minutes >= 24 * 60:
        raise ValueError(f"minutes out of day range: {minutes}")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def add_minutes_hhmm(start_hhmm: str, minutes: int) -> str:
    total = parse_hhmm(start_hhmm) + minutes
    if total >= 24 * 60:
        raise ValueError("booking crosses midnight; same-day sessions only in this version")
    return format_hhmm(total)


def intervals_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    """Half-open overlap: [start, end). Touching endpoints do not conflict."""
    return start_a < end_b and start_b < end_a


def validate_iso_date(value: str) -> str:
    text = value.strip()
    if not _DATE_RE.match(text):
        raise ValueError(f"invalid date: {value!r} (use YYYY-MM-DD)")
    date.fromisoformat(text)  # raises if impossible calendar day
    return text


def parse_datetime_local(value: str) -> datetime:
    """Parse YYYY-MM-DDTHH:MM[:SS] or YYYY-MM-DD HH:MM[:SS] as naive local time."""
    text = value.strip().replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"invalid datetime: {value!r}")


def combine_date_time(session_date: str, hhmm: str) -> datetime:
    d = date.fromisoformat(validate_iso_date(session_date))
    minutes = parse_hhmm(hhmm)
    return datetime(d.year, d.month, d.day, minutes // 60, minutes % 60)


def normalize_label(value: str) -> str:
    text = " ".join(value.split())
    if not text:
        raise ValueError("name/label cannot be empty")
    return text


def labels_match(a: str, b: str) -> bool:
    return normalize_label(a).casefold() == normalize_label(b).casefold()
