"""Completion calls Finance. Network failures are mocked. One test uses real HTTP."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pymssql
import pytest

from app.db import connect
from app.finance_client import FinanceCallError
from app.main import app
from app.migrate import split_batches
from tests.conftest import _env_file, _sa_connection

FINANCE_ROOT = Path(__file__).resolve().parents[2] / "finance"
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


@pytest.fixture()
def client(operations_database):
    return app.test_client()


def _complete():
    return {"performed_date": "2020-06-01", "due_date": "2020-06-15"}


def _past_booking() -> int:
    connection = connect()
    try:
        cursor = connection.cursor(as_dict=True)
        cursor.execute("SELECT id FROM dbo.clinicians WHERE display_name = %s", ("Dr. Vega",))
        clinician_id = int(cursor.fetchone()["id"])
        cursor.execute(
            """
            INSERT INTO dbo.sessions (
                room_label, clinician_id, clinician_label, session_date, start_time, end_time
            )
            OUTPUT INSERTED.id
            VALUES (N'Complete Room', %s, N'Dr. Vega', '2020-06-01', '09:00', '12:00')
            """,
            (clinician_id,),
        )
        session_id = int(cursor.fetchone()["id"])
        cursor.execute(
            """
            INSERT INTO dbo.requests (
                patient_ref, procedure_code, priority, requested_at, ready,
                available_from, available_to, minimum_notice_minutes
            )
            OUTPUT INSERTED.id
            VALUES (
                N'P-9001', N'GASTRO', 1, '2020-06-01T08:00:00', 1,
                '2020-06-01T00:00:00', '2020-06-01T23:00:00', 0
            )
            """
        )
        request_id = int(cursor.fetchone()["id"])
        cursor.execute(
            """
            INSERT INTO dbo.bookings (
                request_id, session_id, start_time, end_time, status, timing_source,
                estimated_duration_minutes, variability_minutes, min_planning_minutes,
                planning_block_minutes, room_turnover_minutes
            )
            OUTPUT INSERTED.id
            VALUES (%s, %s, '09:00', '09:30', N'active', N'catalogue', 30, 0, 30, 30, 10)
            """,
            (request_id, session_id),
        )
        booking_id = int(cursor.fetchone()["id"])
        connection.commit()
        return booking_id
    finally:
        connection.close()


def _status(booking_id: int) -> tuple[str, int | None]:
    connection = connect()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT status, finance_receivable_id FROM dbo.bookings WHERE id = %s",
            (booking_id,),
        )
        status, receivable_id = cursor.fetchone()
        return str(status).strip(), None if receivable_id is None else int(receivable_id)
    finally:
        connection.close()


def test_finance_outage_does_not_fail_operations_health(client, monkeypatch):
    monkeypatch.setenv("FINANCE_SERVICE_URL", "http://127.0.0.1:9")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["db"] == "ok"


def test_successful_completion_stores_the_finance_id(client, monkeypatch):
    booking_id = _past_booking()
    seen = {}

    def succeed(payload):
        seen["payload"] = payload
        return 201, {"id": 77, "expected_fee_cents": 12000}

    monkeypatch.setattr("app.completion.post_receivable", succeed)
    response = client.post(f"/bookings/{booking_id}/complete", json=_complete())
    assert response.status_code == 200
    body = response.get_json()
    assert body["outcome"] == "created"
    assert body["receivable_id"] == 77
    assert body["expected_fee_cents"] == 12000
    assert seen["payload"]["source_booking_id"] == booking_id
    assert "expected_fee_cents" not in seen["payload"]
    assert _status(booking_id) == ("completed", 77)

    def fail_if_called(_payload):
        raise AssertionError("a completed booking must not call Finance again")

    monkeypatch.setattr("app.completion.post_receivable", fail_if_called)
    again = client.post(f"/bookings/{booking_id}/complete", json=_complete())
    assert again.status_code == 200
    assert again.get_json()["outcome"] == "already_completed"
    assert again.get_json()["receivable_id"] == 77


def test_timeout_then_matching_reply_completes_once(client, monkeypatch):
    booking_id = _past_booking()
    calls = {"n": 0}

    def unstable(_payload):
        calls["n"] += 1
        if calls["n"] == 1:
            raise FinanceCallError("timeout", detail="timed out")
        return 200, {"id": 15, "expected_fee_cents": 12000}

    monkeypatch.setattr("app.completion.post_receivable", unstable)
    first = client.post(f"/bookings/{booking_id}/complete", json=_complete())
    assert first.status_code == 503
    assert first.get_json()["booking_status"] == "completion_pending"
    assert _status(booking_id) == ("completion_pending", None)

    second = client.post(f"/bookings/{booking_id}/complete", json=_complete())
    assert second.status_code == 200
    assert second.get_json()["outcome"] == "already_recorded"
    assert _status(booking_id) == ("completed", 15)


@pytest.mark.parametrize(
    ("failure", "http_status", "booking_status"),
    [
        (FinanceCallError("refused"), 503, "active"),
        (FinanceCallError("timeout"), 503, "completion_pending"),
        (FinanceCallError("unreachable"), 503, "completion_pending"),
    ],
)
def test_lost_or_refused_finance_call(client, monkeypatch, failure, http_status, booking_status):
    booking_id = _past_booking()

    def raise_failure(_payload):
        raise failure

    monkeypatch.setattr("app.completion.post_receivable", raise_failure)
    response = client.post(f"/bookings/{booking_id}/complete", json=_complete())
    assert response.status_code == http_status
    assert response.get_json()["booking_status"] == booking_status
    assert _status(booking_id)[0] == booking_status


def test_finance_error_and_conflict_are_not_success(client, monkeypatch):
    booking_id = _past_booking()

    def reject(_payload):
        return 400, {"error": "no fee assumption for GASTRO"}

    monkeypatch.setattr("app.completion.post_receivable", reject)
    rejected = client.post(f"/bookings/{booking_id}/complete", json=_complete())
    assert rejected.status_code == 400
    assert _status(booking_id)[0] == "active"

    def crash(_payload):
        return 500, {"error": "unavailable"}

    monkeypatch.setattr("app.completion.post_receivable", crash)
    unknown = client.post(f"/bookings/{booking_id}/complete", json=_complete())
    assert unknown.status_code == 503
    assert _status(booking_id)[0] == "completion_pending"

    def conflict(_payload):
        return 409, {"error": "receivable already exists for this booking with different details"}

    monkeypatch.setattr("app.completion.post_receivable", conflict)
    mismatched = client.post(f"/bookings/{booking_id}/complete", json=_complete())
    assert mismatched.status_code == 409
    assert _status(booking_id)[0] == "completion_pending"


def test_performed_date_must_match_the_session_date(client, monkeypatch):
    def fail_if_called(_payload):
        raise AssertionError("Finance must not be called for a different performed date")

    monkeypatch.setattr("app.completion.post_receivable", fail_if_called)
    booking_id = _past_booking()
    response = client.post(
        f"/bookings/{booking_id}/complete",
        json={"performed_date": "2020-06-02", "due_date": "2020-06-15"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == (
        "performed date must be the booking's session date (2020-06-01)"
    )
    assert _status(booking_id) == ("active", None)


def test_finance_rejection_while_pending_stays_pending(client, monkeypatch):
    booking_id = _past_booking()
    connection = connect()
    try:
        connection.cursor().execute(
            """
            UPDATE dbo.bookings
            SET status = N'completion_pending', finance_receivable_id = NULL
            WHERE id = %s
            """,
            (booking_id,),
        )
        connection.commit()
    finally:
        connection.close()

    def reject(_payload):
        return 400, {"error": "no fee assumption for GASTRO"}

    monkeypatch.setattr("app.completion.post_receivable", reject)
    response = client.post(f"/bookings/{booking_id}/complete", json=_complete())
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "no fee assumption for GASTRO"
    assert body["booking_status"] == "completion_pending"
    assert _status(booking_id) == ("completion_pending", None)


def test_unreadable_finance_success_is_not_a_completion(client, monkeypatch):
    monkeypatch.setenv("FINANCE_SERVICE_URL", "http://finance.internal")
    booking_id = _past_booking()

    class Response:
        status = 200

        def __init__(self, raw):
            self.raw = raw

        def read(self):
            return self.raw

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        "app.finance_client.urllib.request.urlopen",
        lambda *_args, **_kwargs: Response(b"not-json"),
    )
    response = client.post(f"/bookings/{booking_id}/complete", json=_complete())
    assert response.status_code == 503
    assert response.get_json() == {
        "error": "finance result is unknown; the booking stays completion_pending",
        "booking_status": "completion_pending",
    }
    assert _status(booking_id) == ("completion_pending", None)


def test_cancelled_booking_and_bad_dates_do_not_call_finance(client, monkeypatch):
    def fail_if_called(_payload):
        raise AssertionError("Finance must not be called")

    monkeypatch.setattr("app.completion.post_receivable", fail_if_called)
    booking_id = _past_booking()
    missing = client.post("/bookings/999999/complete", json=_complete())
    assert missing.status_code == 404

    early = client.post(
        f"/bookings/{booking_id}/complete",
        json={"performed_date": "2020-06-01", "due_date": "2020-05-01"},
    )
    assert early.status_code == 400
    assert "due date" in early.get_json()["error"]

    connection = connect()
    try:
        connection.cursor().execute(
            "UPDATE dbo.bookings SET status = N'cancelled' WHERE id = %s",
            (booking_id,),
        )
        connection.commit()
    finally:
        connection.close()
    cancelled = client.post(f"/bookings/{booking_id}/complete", json=_complete())
    assert cancelled.status_code == 400
    assert "cancelled" in cancelled.get_json()["error"]
    assert _status(booking_id)[0] == "cancelled"


def test_booking_that_has_not_started_stays_active(client, monkeypatch):
    def fail_if_called(_payload):
        raise AssertionError("Finance must not be called before the booking starts")

    monkeypatch.setattr("app.completion.post_receivable", fail_if_called)
    session = client.post(
        "/sessions",
        json={
            "room_label": "Future Room",
            "clinician_label": "Dr. Vega",
            "session_date": "2099-01-01",
            "start_time": "09:00",
            "end_time": "12:00",
        },
    ).get_json()
    booked = client.post(
        "/bookings",
        json={
            "session_id": session["id"],
            "start_time": "09:00",
            "patient_ref": "P-9002",
            "procedure_code": "GASTRO",
            "priority": 1,
            "ready": True,
            "available_from": "2099-01-01T00:00:00",
            "available_to": "2099-01-01T18:00:00",
            "minimum_notice_minutes": 0,
            "requested_at": "2098-12-01T08:00:00",
        },
    )
    assert booked.status_code == 201
    response = client.post(
        f"/bookings/{booked.get_json()['id']}/complete",
        json={"performed_date": "2099-01-01", "due_date": "2099-01-10"},
    )
    assert response.status_code == 400
    assert "not started" in response.get_json()["error"]


def test_completion_migration_keeps_an_existing_booking():
    admin = _sa_connection()
    cursor = admin.cursor()
    cursor.execute(
        """
        IF DB_ID(N'operations_migration_probe') IS NOT NULL
        BEGIN
            ALTER DATABASE operations_migration_probe SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
            DROP DATABASE operations_migration_probe;
        END
        """
    )
    cursor.execute("CREATE DATABASE operations_migration_probe")
    admin.close()
    values = _env_file()
    host = os.environ.get("SQL_HOST", "127.0.0.1")
    port = int(os.environ.get("SQL_PORT") or values.get("SQL_PORT") or "1433")
    probe = pymssql.connect(
        server=host,
        port=port,
        user="sa",
        password=os.environ.get("MSSQL_SA_PASSWORD") or values["MSSQL_SA_PASSWORD"],
        database="operations_migration_probe",
        login_timeout=3,
        autocommit=True,
    )
    try:
        writer = probe.cursor()
        for name in ("001_sessions.sql", "002_bookings.sql"):
            for batch in split_batches((MIGRATIONS / name).read_text(encoding="utf-8")):
                writer.execute(batch)
        writer.execute("INSERT INTO dbo.clinicians (display_name) OUTPUT INSERTED.id VALUES (N'Dr. Vega')")
        clinician_id = int(writer.fetchone()[0])
        writer.execute(
            """
            INSERT INTO dbo.procedure_types (
                code, display_name, duration_minutes, turnover_minutes, min_planning_minutes
            ) VALUES (N'GASTRO', N'Gastroscopy', 30, 10, 30)
            """
        )
        writer.execute(
            """
            INSERT INTO dbo.sessions (
                room_label, clinician_id, clinician_label, session_date, start_time, end_time
            )
            OUTPUT INSERTED.id
            VALUES (N'Probe Room', %s, N'Dr. Vega', '2020-06-01', '09:00', '12:00')
            """,
            (clinician_id,),
        )
        session_id = int(writer.fetchone()[0])
        writer.execute(
            """
            INSERT INTO dbo.requests (
                patient_ref, procedure_code, priority, requested_at, ready,
                available_from, available_to, minimum_notice_minutes
            )
            OUTPUT INSERTED.id
            VALUES (N'P-1', N'GASTRO', 1, '2020-06-01T08:00:00', 1,
                    '2020-06-01T00:00:00', '2020-06-01T23:00:00', 0)
            """
        )
        request_id = int(writer.fetchone()[0])
        writer.execute(
            """
            INSERT INTO dbo.bookings (
                request_id, session_id, start_time, end_time, status, timing_source,
                estimated_duration_minutes, variability_minutes, min_planning_minutes,
                planning_block_minutes, room_turnover_minutes
            )
            OUTPUT INSERTED.id
            VALUES (%s, %s, '09:00', '09:30', N'active', N'catalogue', 30, 0, 30, 30, 10)
            """,
            (request_id, session_id),
        )
        booking_id = int(writer.fetchone()[0])
        for batch in split_batches((MIGRATIONS / "003_completion_state.sql").read_text(encoding="utf-8")):
            writer.execute(batch)
        writer.execute(
            "SELECT status, finance_receivable_id FROM dbo.bookings WHERE id = %s",
            (booking_id,),
        )
        status, receivable_id = writer.fetchone()
        assert str(status).strip() == "active"
        assert receivable_id is None
        writer.execute("SELECT COUNT(*) FROM dbo.bookings")
        assert writer.fetchone()[0] == 1
        writer.execute(
            "UPDATE dbo.bookings SET status = N'completion_pending' WHERE id = %s",
            (booking_id,),
        )
    finally:
        probe.close()
        cleanup = _sa_connection()
        cleanup.cursor().execute(
            """
            IF DB_ID(N'operations_migration_probe') IS NOT NULL
            BEGIN
                ALTER DATABASE operations_migration_probe SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
                DROP DATABASE operations_migration_probe;
            END
            """
        )
        cleanup.close()


def test_real_finance_service_creates_one_receivable(client, monkeypatch):
    values = _env_file()
    password = (
        os.environ.get("FINANCE_DB_PASSWORD")
        or values.get("FINANCE_DB_PASSWORD")
        or "FinanceTestOnly1"
    )
    host = os.environ.get("SQL_HOST", "127.0.0.1")
    port_sql = int(os.environ.get("SQL_PORT") or values.get("SQL_PORT") or "1433")
    admin = _sa_connection()
    admin_cursor = admin.cursor()
    admin_cursor.execute(
        """
        IF DB_ID(N'finance_completion_test') IS NOT NULL
        BEGIN
            ALTER DATABASE finance_completion_test SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
            DROP DATABASE finance_completion_test;
        END
        """
    )
    admin_cursor.execute("CREATE DATABASE finance_completion_test")
    admin_cursor.execute(
        """
        IF SUSER_ID(N'finance_completion_user') IS NULL
            CREATE LOGIN finance_completion_user WITH PASSWORD = %s, CHECK_POLICY = OFF
        ELSE
            ALTER LOGIN finance_completion_user WITH PASSWORD = %s
        """,
        (password, password),
    )
    admin.close()
    owner = pymssql.connect(
        server=host,
        port=port_sql,
        user="sa",
        password=os.environ.get("MSSQL_SA_PASSWORD") or values["MSSQL_SA_PASSWORD"],
        database="finance_completion_test",
        login_timeout=3,
        autocommit=True,
    )
    owner.cursor().execute(
        """
        IF USER_ID(N'finance_completion_user') IS NULL
            CREATE USER finance_completion_user FOR LOGIN finance_completion_user
        """
    )
    owner.cursor().execute("ALTER ROLE db_owner ADD MEMBER finance_completion_user")
    owner.close()

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        http_port = probe.getsockname()[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = (
        f"mssql://finance_completion_user:{password}@{host}:{port_sql}/finance_completion_test"
    )
    env["PORT"] = str(http_port)
    process = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=FINANCE_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                time.sleep(0.25)
        else:
            pytest.fail("the finance service did not become healthy")

        monkeypatch.setenv("FINANCE_SERVICE_URL", f"http://127.0.0.1:{http_port}")
        monkeypatch.setenv("FINANCE_TIMEOUT_SECONDS", "3")
        booking_id = _past_booking()
        first = client.post(f"/bookings/{booking_id}/complete", json=_complete())
        assert first.status_code == 200, first.get_json()
        assert first.get_json()["expected_fee_cents"] == 12000
        second = client.post(f"/bookings/{booking_id}/complete", json=_complete())
        assert second.status_code == 200
        assert second.get_json()["receivable_id"] == first.get_json()["receivable_id"]

        retry = connect()
        try:
            retry.cursor().execute(
                """
                UPDATE dbo.bookings
                SET status = N'completion_pending', finance_receivable_id = NULL
                WHERE id = %s
                """,
                (booking_id,),
            )
            retry.commit()
        finally:
            retry.close()
        recovered = client.post(f"/bookings/{booking_id}/complete", json=_complete())
        assert recovered.status_code == 200
        assert recovered.get_json()["outcome"] == "already_recorded"
        assert recovered.get_json()["receivable_id"] == first.get_json()["receivable_id"]

        check = pymssql.connect(
            server=host,
            port=port_sql,
            user="sa",
            password=os.environ.get("MSSQL_SA_PASSWORD") or values["MSSQL_SA_PASSWORD"],
            database="finance_completion_test",
            login_timeout=3,
        )
        try:
            cursor = check.cursor()
            cursor.execute("SELECT COUNT(*) FROM dbo.receivables")
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = N'bookings'"
            )
            assert cursor.fetchone()[0] == 0
        finally:
            check.close()
        assert _status(booking_id)[0] == "completed"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        cleanup = _sa_connection()
        cleanup.cursor().execute(
            """
            IF DB_ID(N'finance_completion_test') IS NOT NULL
            BEGIN
                ALTER DATABASE finance_completion_test SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
                DROP DATABASE finance_completion_test;
            END
            """
        )
        cleanup.close()
