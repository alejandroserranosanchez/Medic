"""Pure money-status rules. Amounts are integer euro cents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BalanceView:
    expected_fee_cents: int
    paid_cents: int
    balance_cents: int
    status: str  # unpaid | partial | settled | overpaid
    overdue: bool


def classify_balance(
    *,
    expected_fee_cents: int,
    paid_cents: int,
    due_date: str,
    as_of_date: str,
) -> BalanceView:
    if expected_fee_cents < 0 or paid_cents < 0:
        raise ValueError("money amounts cannot be negative")

    balance = expected_fee_cents - paid_cents
    if paid_cents == 0 and expected_fee_cents > 0:
        status = "unpaid"
    elif paid_cents > expected_fee_cents:
        status = "overpaid"
    elif paid_cents == expected_fee_cents:
        status = "settled"
    else:
        status = "partial"

    overdue = balance > 0 and as_of_date > due_date
    return BalanceView(
        expected_fee_cents=expected_fee_cents,
        paid_cents=paid_cents,
        balance_cents=balance,
        status=status,
        overdue=overdue,
    )
