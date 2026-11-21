"""Small text checks used by Finance. Dates stay YYYY-MM-DD."""

from __future__ import annotations

import re
from datetime import date


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_iso_date(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid date: {value!r} (use YYYY-MM-DD)")
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
