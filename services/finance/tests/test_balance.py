"""Money labels copied from the original clinic. These do not need SQL Server."""

import pytest

from app.receivables import FinanceError, classify_balance


@pytest.mark.parametrize(
    ("expected", "paid", "status", "balance"),
    [
        (12000, 0, "unpaid", 12000),
        (12000, 9000, "partial", 3000),
        (12000, 12000, "settled", 0),
        (12000, 13000, "overpaid", -1000),
        (0, 0, "settled", 0),
    ],
)
def test_balance_status_labels(expected, paid, status, balance):
    view = classify_balance(
        expected_fee_cents=expected,
        paid_cents=paid,
        due_date="2026-10-20",
        as_of_date="2026-10-09",
    )
    assert view["status"] == status
    assert view["balance_cents"] == balance


def test_overdue_only_when_money_is_still_owed_after_the_due_date():
    late = classify_balance(
        expected_fee_cents=12000,
        paid_cents=9000,
        due_date="2026-10-01",
        as_of_date="2026-10-09",
    )
    settled = classify_balance(
        expected_fee_cents=12000,
        paid_cents=12000,
        due_date="2026-10-01",
        as_of_date="2026-10-09",
    )
    assert late["overdue"] is True
    assert settled["overdue"] is False


def test_negative_amounts_are_rejected():
    with pytest.raises(FinanceError, match="negative"):
        classify_balance(
            expected_fee_cents=-1,
            paid_cents=0,
            due_date="2026-10-20",
            as_of_date="2026-10-09",
        )
