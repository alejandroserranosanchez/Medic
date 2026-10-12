"""Finance rules + application-service completion boundary."""

from __future__ import annotations

from datetime import datetime

import pytest

from clinic.application import CompletionError, complete_booking
from clinic.db import get_db
from clinic.finance import repository as finance_repo
from clinic.finance.reconciliation import classify_balance
from clinic.finance.repository import FinanceError
from clinic.operations import repository as ops_repo

# Seeded P-1001 booking starts 2026-10-10 09:00.
AFTER_START = datetime(2026, 10, 10, 10, 0, 0)


@pytest.mark.parametrize(
    "expected, paid, status, balance",
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
    assert view.status == status
    assert view.balance_cents == balance


def test_overdue_only_when_balance_positive_after_due_date():
    late = classify_balance(
        expected_fee_cents=12000, paid_cents=9000, due_date="2026-10-01", as_of_date="2026-10-09"
    )
    assert late.overdue is True

    settled_late = classify_balance(
        expected_fee_cents=12000, paid_cents=12000, due_date="2026-10-01", as_of_date="2026-10-09"
    )
    assert settled_late.overdue is False


def test_negative_amounts_rejected():
    with pytest.raises(ValueError, match="negative"):
        classify_balance(
            expected_fee_cents=-1, paid_cents=0, due_date="2026-10-20", as_of_date="2026-10-09"
        )


def test_complete_booking_creates_one_receivable(app):
    with app.app_context():
        db = get_db()
        booking = next(b for b in ops_repo.list_bookings(db) if b["patient_ref"] == "P-1001")
        rid = complete_booking(
            db,
            booking_id=booking["id"],
            performed_date="2026-10-10",
            now=AFTER_START,
            due_date="2026-10-23",
        )
        row = db.execute("SELECT * FROM receivables WHERE id = ?", (rid,)).fetchone()
        assert row["source_booking_id"] == booking["id"]
        assert row["expected_fee_cents"] == 12000  # GASTRO seed fee snapshot

        db.execute(
            "UPDATE fee_assumptions SET expected_fee_cents = 99999 WHERE procedure_code = 'GASTRO'"
        )
        row = db.execute("SELECT * FROM receivables WHERE id = ?", (rid,)).fetchone()
        assert row["expected_fee_cents"] == 12000

        # Idempotent re-complete
        rid2 = complete_booking(
            db,
            booking_id=booking["id"],
            performed_date="2026-10-10",
            now=AFTER_START,
            due_date="2026-10-23",
        )
        assert rid2 == rid
        n = db.execute("SELECT COUNT(*) AS n FROM receivables").fetchone()["n"]
        assert n == 1


def test_cancel_cannot_complete(app):
    with app.app_context():
        db = get_db()
        booking = next(b for b in ops_repo.list_bookings(db) if b["patient_ref"] == "P-1001")
        ops_repo.cancel_booking(db, booking["id"])
        with pytest.raises(CompletionError, match="only active"):
            complete_booking(
                db,
                booking_id=booking["id"],
                performed_date="2026-10-10",
            now=AFTER_START,
                due_date="2026-10-23",
            )
        assert db.execute("SELECT COUNT(*) AS n FROM receivables").fetchone()["n"] == 0


def test_cannot_complete_booking_before_it_starts(app):
    with app.app_context():
        db = get_db()
        booking = next(b for b in ops_repo.list_bookings(db) if b["patient_ref"] == "P-1001")

        with pytest.raises(CompletionError, match="not started yet"):
            complete_booking(
                db,
                booking_id=booking["id"],
                performed_date="2026-10-10",
                due_date="2026-10-24",
                now=datetime(2026, 10, 10, 8, 59, 0),
            )

        assert db.execute("SELECT COUNT(*) AS n FROM receivables").fetchone()["n"] == 0
        status = db.execute("SELECT status FROM bookings WHERE id = ?", (booking["id"],)).fetchone()["status"]
        assert status == "active"


@pytest.mark.parametrize(
    "performed, due, message",
    [
        ("2026-10-09", "2026-10-24", "session date"),
        ("2026-10-10", "2026-10-09", "due date cannot be before"),
    ],
)
def test_completion_dates_must_match_the_booking(app, performed, due, message):
    with app.app_context():
        db = get_db()
        booking = next(b for b in ops_repo.list_bookings(db) if b["patient_ref"] == "P-1001")

        with pytest.raises(CompletionError, match=message):
            complete_booking(
                db,
                booking_id=booking["id"],
                performed_date=performed,
                due_date=due,
                now=AFTER_START,
            )


def test_payments_partial_duplicate_and_settle(app):
    with app.app_context():
        db = get_db()
        booking = next(b for b in ops_repo.list_bookings(db) if b["patient_ref"] == "P-1001")
        rid = complete_booking(
            db,
            booking_id=booking["id"],
            performed_date="2026-10-10",
            now=AFTER_START,
            due_date="2026-10-23",
        )
        p1 = finance_repo.record_payment(
            db,
            receivable_id=rid,
            payment_reference="P1",
            amount_cents=9000,
            paid_date="2026-10-09",
        )
        # Same reference + same details → idempotent
        p1b = finance_repo.record_payment(
            db,
            receivable_id=rid,
            payment_reference="P1",
            amount_cents=9000,
            paid_date="2026-10-09",
        )
        assert p1b == p1

        with pytest.raises(FinanceError, match="different details"):
            finance_repo.record_payment(
                db,
                receivable_id=rid,
                payment_reference="P1",
                amount_cents=1000,
                paid_date="2026-10-09",
            )

        finance_repo.record_payment(
            db,
            receivable_id=rid,
            payment_reference="P2",
            amount_cents=3000,
            paid_date="2026-10-09",
        )
        views = finance_repo.list_receivables(db, as_of_date="2026-10-09")
        item = next(v for v in views if v["id"] == rid)
        assert item["balance"].status == "settled"
        assert item["balance"].paid_cents == 12000
