"""Finance HTTP API against SQL Server. Skipped when no server is reachable."""

from __future__ import annotations

import pytest

from app.db import connect
from app.main import app
from app.migrate import apply_migrations


@pytest.fixture()
def client(finance_database):
    apply_migrations()
    return app.test_client()


def _receivable(**overrides):
    body = {
        "source_booking_id": 41,
        "procedure_code": "gastro",
        "performed_date": "2026-11-20",
        "due_date": "2026-12-20",
        "expected_fee_cents": 12000,
    }
    body.update(overrides)
    return body


def _payment(**overrides):
    body = {
        "payment_reference": "PAY-9000",
        "amount_cents": 9000,
        "paid_date": "2026-11-21",
    }
    body.update(overrides)
    return body


def test_create_then_fetch_a_receivable(client):
    created = client.post("/receivables", json=_receivable())
    assert created.status_code == 201
    body = created.get_json()
    assert body["source_booking_id"] == 41
    assert body["procedure_code"] == "GASTRO"
    assert body["expected_fee_cents"] == 12000
    assert body["performed_date"] == "2026-11-20"
    assert body["due_date"] == "2026-12-20"

    fetched = client.get(f"/receivables/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json() == body


def test_partial_payment_then_the_remaining_balance(client):
    receivable = client.post("/receivables", json=_receivable()).get_json()
    paid = client.post(f"/receivables/{receivable['id']}/payments", json=_payment())
    assert paid.status_code == 201
    assert paid.get_json()["amount_cents"] == 9000

    balance = client.get(f"/receivables/{receivable['id']}/balance?as_of=2026-11-21")
    assert balance.status_code == 200
    body = balance.get_json()
    assert body["paid_cents"] == 9000
    assert body["balance_cents"] == 3000
    assert body["status"] == "partial"
    assert body["overdue"] is False
    assert len(body["payments"]) == 1

    late = client.get(f"/receivables/{receivable['id']}/balance?as_of=2026-12-21").get_json()
    assert late["overdue"] is True
    bad_date = client.get(f"/receivables/{receivable['id']}/balance?as_of=tomorrow")
    assert bad_date.status_code == 400


def test_full_payment_settles_and_extra_payment_is_overpaid(client):
    receivable = client.post("/receivables", json=_receivable()).get_json()
    assert client.post(
        f"/receivables/{receivable['id']}/payments", json=_payment()
    ).status_code == 201
    rest = client.post(
        f"/receivables/{receivable['id']}/payments",
        json=_payment(payment_reference="PAY-3000", amount_cents=3000),
    )
    assert rest.status_code == 201
    settled = client.get(f"/receivables/{receivable['id']}/balance?as_of=2026-12-21").get_json()
    assert settled["status"] == "settled"
    assert settled["balance_cents"] == 0
    assert settled["overdue"] is False

    extra = client.post(
        f"/receivables/{receivable['id']}/payments",
        json=_payment(payment_reference="PAY-EXTRA", amount_cents=1000),
    )
    assert extra.status_code == 201
    overpaid = client.get(f"/receivables/{receivable['id']}/balance?as_of=2026-12-21").get_json()
    assert overpaid["paid_cents"] == 13000
    assert overpaid["balance_cents"] == -1000
    assert overpaid["status"] == "overpaid"


def test_same_payment_reference_is_stored_once(client):
    receivable = client.post("/receivables", json=_receivable()).get_json()
    first = client.post(f"/receivables/{receivable['id']}/payments", json=_payment())
    second = client.post(f"/receivables/{receivable['id']}/payments", json=_payment())
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.get_json()["id"] == first.get_json()["id"]

    balance = client.get(f"/receivables/{receivable['id']}/balance").get_json()
    assert balance["paid_cents"] == 9000
    assert len(balance["payments"]) == 1


def test_same_reference_with_different_details_conflicts(client):
    receivable = client.post("/receivables", json=_receivable()).get_json()
    other = client.post("/receivables", json=_receivable(source_booking_id=42)).get_json()
    assert client.post(
        f"/receivables/{receivable['id']}/payments", json=_payment()
    ).status_code == 201
    conflict = client.post(
        f"/receivables/{receivable['id']}/payments",
        json=_payment(amount_cents=1000),
    )
    assert conflict.status_code == 409
    assert "different details" in conflict.get_json()["error"]
    other_charge = client.post(f"/receivables/{other['id']}/payments", json=_payment())
    assert other_charge.status_code == 409
    balance = client.get(f"/receivables/{receivable['id']}/balance").get_json()
    assert balance["paid_cents"] == 9000


def test_invalid_money_and_dates_are_rejected(client):
    missing = client.post("/receivables", json={})
    assert missing.status_code == 400
    assert "missing field" in missing.get_json()["error"]

    text = client.post("/receivables", data="not-json", content_type="application/json")
    assert text.status_code == 400

    negative = client.post("/receivables", json=_receivable(expected_fee_cents=-1))
    assert negative.status_code == 400

    early = client.post("/receivables", json=_receivable(due_date="2026-11-19"))
    assert early.status_code == 400
    assert "due date" in early.get_json()["error"]

    receivable = client.post("/receivables", json=_receivable()).get_json()
    zero = client.post(
        f"/receivables/{receivable['id']}/payments",
        json=_payment(amount_cents=0),
    )
    assert zero.status_code == 400
    assert "positive" in zero.get_json()["error"]

    blank = client.post(
        f"/receivables/{receivable['id']}/payments",
        json=_payment(payment_reference="  "),
    )
    assert blank.status_code == 400


def test_unknown_receivable_is_404(client):
    assert client.get("/receivables/999999").status_code == 404
    assert client.get("/receivables/999999/balance").status_code == 404
    missing = client.post("/receivables/999999/payments", json=_payment())
    assert missing.status_code == 404
    assert missing.get_json()["error"] == "receivable not found"


def test_identical_receivable_is_not_duplicated(client):
    first = client.post("/receivables", json=_receivable())
    second = client.post("/receivables", json=_receivable())
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.get_json()["id"] == first.get_json()["id"]
    connection = connect()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM dbo.receivables")
        assert cursor.fetchone()[0] == 1
    finally:
        connection.close()


def test_omitted_fee_uses_the_established_catalogue(client):
    body = _receivable(source_booking_id=77)
    del body["expected_fee_cents"]
    created = client.post("/receivables", json=body)
    assert created.status_code == 201
    assert created.get_json()["expected_fee_cents"] == 12000

    unknown_body = _receivable(procedure_code="UNKNOWN", source_booking_id=78)
    del unknown_body["expected_fee_cents"]
    missing = client.post("/receivables", json=unknown_body)
    assert missing.status_code == 400
    assert "no fee assumption" in missing.get_json()["error"]


def test_duplicate_booking_id_is_a_conflict_and_rows_survive(client):
    created = client.post("/receivables", json=_receivable())
    assert created.status_code == 201
    receivable_id = created.get_json()["id"]
    again = client.post("/receivables", json=_receivable(expected_fee_cents=100))
    assert again.status_code == 409

    client.post(f"/receivables/{receivable_id}/payments", json=_payment())
    connection = connect()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM dbo.receivables")
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT expected_fee_cents FROM dbo.receivables WHERE id = %s",
            (receivable_id,),
        )
        assert cursor.fetchone()[0] == 12000
        cursor.execute("SELECT COUNT(*) FROM dbo.payments")
        assert cursor.fetchone()[0] == 1
    finally:
        connection.close()

    fetched = client.get(f"/receivables/{receivable_id}")
    assert fetched.status_code == 200
    assert fetched.get_json()["expected_fee_cents"] == 12000
