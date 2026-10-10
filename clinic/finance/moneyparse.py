"""Parse user EUR amounts into integer cents (max 2 decimals; no binary floats)."""

from __future__ import annotations


def euros_to_cents(raw: str) -> int:
    text = raw.strip().replace(",", ".")
    if not text or text.count(".") > 1:
        raise ValueError("invalid amount")
    negative = text.startswith("-")
    if negative:
        raise ValueError("amount cannot be negative")
    if "." in text:
        whole, frac = text.split(".", 1)
        if whole == "":
            whole = "0"
        if not whole.isdigit() or not frac.isdigit():
            raise ValueError("invalid amount")
        if len(frac) > 2:
            raise ValueError("use at most 2 decimal places")
        frac = (frac + "00")[:2]
        return int(whole) * 100 + int(frac)
    if not text.isdigit():
        raise ValueError("invalid amount")
    return int(text) * 100


def cents_to_euros(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    value = abs(cents)
    return f"{sign}{value // 100}.{value % 100:02d}"
