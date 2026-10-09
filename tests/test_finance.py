"""Finance rules + application-service completion boundary."""

from __future__ import annotations

import pytest

from clinic.application import complete_booking
from clinic.db import get_db
from clinic.finance import repository as finance_repo
from clinic.finance.reconciliation import classify_balance
from clinic.finance.repository import FinanceError
from clinic.operations import repository as ops_repo
from clinic.operations.service import OperationsError


def test_partial_then_settle_labels():
    first = classify_balance(
        expected_fee_cents=12000,
        paid_cents=9000,
        due_date="2026-10-20",
        as_of_date="2026-10-09",
    )
    assert first.status == "partial"
    assert first.balance_cents == 3000

    settled = classify_balance(
        expected_fee_cents=12000,
        paid_cents=12000,
        due_date="2026-10-20",
        as_of_date="2026-10-09",
    )
    assert settled.status == "settled"


def test_overpaid_and_zero_expected_settled():
    over = classify_balance(
        expected_fee_cents=12000,
        paid_cents=13000,
        due_date="2026-10-20",
        as_of_date="2026-10-09",
    )
    assert over.status == "overpaid"
    assert over.balance_cents == -1000

    zero = classify_balance(
        expected_fee_cents=0,
        paid_cents=0,
        due_date="2026-10-20",
        as_of_date="2026-10-09",
    )
    assert zero.status == "settled"


def test_complete_booking_creates_one_receivable(app):
    with app.app_context():
        db = get_db()
        booking = next(b for b in ops_repo.list_bookings(db) if b["status"] == "active")
        rid = complete_booking(
            db,
            booking_id=booking["id"],
            performed_date="2026-10-09",
            due_date="2026-10-23",
        )
        row = db.execute("SELECT * FROM receivables WHERE id = ?", (rid,)).fetchone()
        assert row["source_booking_id"] == booking["id"]
        assert row["expected_fee_cents"] == 12000  # GASTRO seed fee snapshot

        # Idempotent re-complete
        rid2 = complete_booking(
            db,
            booking_id=booking["id"],
            performed_date="2026-10-09",
            due_date="2026-10-23",
        )
        assert rid2 == rid
        n = db.execute("SELECT COUNT(*) AS n FROM receivables").fetchone()["n"]
        assert n == 1


def test_cancel_cannot_complete(app):
    with app.app_context():
        db = get_db()
        booking = next(b for b in ops_repo.list_bookings(db) if b["status"] == "active")
        ops_repo.cancel_booking(db, booking["id"])
        with pytest.raises(OperationsError):
            complete_booking(
                db,
                booking_id=booking["id"],
                performed_date="2026-10-09",
                due_date="2026-10-23",
            )
        assert db.execute("SELECT COUNT(*) AS n FROM receivables").fetchone()["n"] == 0


def test_payments_partial_duplicate_and_settle(app):
    with app.app_context():
        db = get_db()
        booking = next(b for b in ops_repo.list_bookings(db) if b["status"] == "active")
        rid = complete_booking(
            db,
            booking_id=booking["id"],
            performed_date="2026-10-09",
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
