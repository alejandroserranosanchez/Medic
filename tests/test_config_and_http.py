"""Deployment contract (env config) and thin HTTP checks: happy path, invalid input, duplicates."""

from __future__ import annotations

from datetime import datetime

from clinic import create_app
from clinic.clock import now
from clinic.db import get_db


def test_port_and_data_dir_come_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PORT", "9123")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "env-data"))

    app = create_app({"TESTING": True})

    assert app.config["PORT"] == 9123
    assert app.config["HOST"] == "0.0.0.0"
    assert (tmp_path / "env-data" / "clinic.sqlite3").exists()


def test_demo_now_overrides_clock(monkeypatch):
    monkeypatch.setenv("DEMO_NOW", "2026-10-09T12:00:00")

    assert now() == datetime(2026, 10, 9, 12, 0, 0)


def test_main_pages_load(client):
    for path in ("/", "/capacity", "/payments", "/investment"):
        assert client.get(path).status_code == 200


def test_schedule_offers_mark_as_done_only_for_started_bookings(client):
    page = client.get("/capacity").data

    assert page.count(b"Mark as done</button>") == 1
    assert b"Past session" in page
    assert b"Unused</span>" in page


def test_invalid_request_form_shows_error_not_500(client):
    resp = client.post(
        "/capacity/requests",
        data={
            "patient_ref": "P-BAD",
            "procedure_code": "GASTRO",
            "priority": "1",
            "requested_at": "2026-10-09T10:00:00",
            "available_from": "2026-10-10T09:00:00",
            "available_to": "2026-10-10T18:00:00",
            "minimum_notice_minutes": "-1",
        },
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"minimum notice cannot be negative" in resp.data


def _seeded_booking_id(app):
    with app.app_context():
        return get_db().execute(
            """
            SELECT b.id FROM bookings b JOIN requests r ON r.id = b.request_id
            WHERE r.patient_ref = 'P-1001'
            """
        ).fetchone()["id"]


def test_mark_as_done_before_start_is_refused(app, client):
    booking_id = _seeded_booking_id(app)

    resp = client.post(
        f"/payments/complete/{booking_id}",
        data={"performed_date": "2026-10-10", "due_date": "2026-10-24"},
        follow_redirects=True,
    )

    assert b"has not started yet" in resp.data
    with app.app_context():
        n = get_db().execute("SELECT COUNT(*) AS n FROM receivables").fetchone()["n"]
    assert n == 0


def test_completing_same_booking_twice_creates_one_receivable(app, client):
    booking_id = _seeded_booking_id(app)
    app.config["DEMO_NOW"] = "2026-10-10T10:00:00"

    form = {"performed_date": "2026-10-10", "due_date": "2026-10-24"}
    first = client.post(f"/payments/complete/{booking_id}", data=form)
    second = client.post(f"/payments/complete/{booking_id}", data=form)

    assert first.status_code == 302
    assert second.status_code == 302
    with app.app_context():
        n = get_db().execute("SELECT COUNT(*) AS n FROM receivables").fetchone()["n"]
    assert n == 1


def test_bad_euro_amount_is_rejected(app, client):
    booking_id = _seeded_booking_id(app)
    app.config["DEMO_NOW"] = "2026-10-10T10:00:00"
    client.post(
        f"/payments/complete/{booking_id}",
        data={"performed_date": "2026-10-10", "due_date": "2026-10-24"},
    )

    resp = client.post(
        "/payments/record",
        data={
            "receivable_id": "1",
            "payment_reference": "P1",
            "amount_eur": "90.123",
            "paid_date": "2026-10-09",
        },
        follow_redirects=True,
    )

    assert b"at most 2 decimal places" in resp.data
    with app.app_context():
        n = get_db().execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]
    assert n == 0
