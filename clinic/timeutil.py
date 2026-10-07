"""Small time helpers. Store clock times as HH:MM strings; compare as minutes."""

from __future__ import annotations


def parse_hhmm(value: str) -> int:
    """Return minutes from midnight for 'HH:MM'."""
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"invalid time: {value!r}")
    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid time: {value!r}")
    return hour * 60 + minute


def format_hhmm(minutes: int) -> str:
    if minutes < 0 or minutes >= 24 * 60:
        raise ValueError(f"minutes out of day range: {minutes}")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def intervals_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    """Half-open overlap: [start, end). Touching endpoints do not conflict."""
    return start_a < end_b and start_b < end_a
