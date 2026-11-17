"""API tests against SQL Server. Skipped when no server is reachable."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pymssql
import pytest

from app.main import app
from app.migrate import apply_migrations
from app.seed import seed_clinicians

ROOT = Path(__file__).resolve().parents[3]


def _env_file() -> dict[str, str]:
    path = ROOT / ".env"
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _sa_connection():
    values = _env_file()
    password = os.environ.get("MSSQL_SA_PASSWORD") or values.get("MSSQL_SA_PASSWORD")
    host = os.environ.get("SQL_HOST", "127.0.0.1")
    port = int(os.environ.get("SQL_PORT") or values.get("SQL_PORT") or "1433")
    if not password:
        pytest.skip("SQL Server admin password is not available")
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except OSError:
        pytest.skip("SQL Server port is not accepting connections")
    try:
        return pymssql.connect(
            server=host,
            port=port,
            user="sa",
            password=password,
            database="master",
            login_timeout=3,
            autocommit=True,
        )
    except pymssql.Error as exc:
        pytest.skip(f"SQL Server is not reachable: {exc.__class__.__name__}")


@pytest.fixture()
def operations_database():
    values = _env_file()
    password = os.environ.get("OPERATIONS_DB_PASSWORD") or values.get("OPERATIONS_DB_PASSWORD")
    host = os.environ.get("SQL_HOST", "127.0.0.1")
    port = int(os.environ.get("SQL_PORT") or values.get("SQL_PORT") or "1433")
    if not password:
        pytest.skip("Operations database password is not available")
    admin = _sa_connection()
    cursor = admin.cursor()
    cursor.execute("IF DB_ID(N'operations_test') IS NULL CREATE DATABASE operations_test")
    cursor.execute(
        """
        IF SUSER_ID(N'operations_user') IS NULL
            CREATE LOGIN operations_user WITH PASSWORD = %s, CHECK_POLICY = OFF
        """,
        (password,),
    )
    admin.close()
    owner = pymssql.connect(
        server=host,
        port=port,
        user="sa",
        password=os.environ.get("MSSQL_SA_PASSWORD") or values["MSSQL_SA_PASSWORD"],
        database="operations_test",
        login_timeout=3,
        autocommit=True,
    )
    owner.cursor().execute(
        """
        IF USER_ID(N'operations_user') IS NULL
            CREATE USER operations_user FOR LOGIN operations_user
        """
    )
    owner.cursor().execute(
        """
        IF IS_ROLEMEMBER(N'db_owner', N'operations_user') <> 1
            ALTER ROLE db_owner ADD MEMBER operations_user
        """
    )
    owner.close()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = (
        f"mssql://operations_user:{password}@{host}:{port}/operations_test"
    )
    from app.db import connect

    connection = connect()
    apply_migrations(connection)
    seed_clinicians(connection)
    from app.seed import seed_catalogue

    seed_catalogue(connection)
    cursor = connection.cursor()
    cursor.execute("DELETE FROM dbo.bookings")
    cursor.execute("DELETE FROM dbo.requests")
    cursor.execute("DELETE FROM dbo.sessions")
    connection.commit()
    connection.close()
    yield
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous


@pytest.fixture()
def client(operations_database):
    return app.test_client()


def _payload(room, start="09:00", end="12:00", clinician="Dr. Vega"):
    return {
        "room_label": room,
        "clinician_label": clinician,
        "session_date": "2099-01-01",
        "start_time": start,
        "end_time": end,
    }


def test_create_then_fetch_session(client):
    created = client.post("/sessions", json=_payload("Notes Room"))
    assert created.status_code == 201
    body = created.get_json()
    assert body["clinician_label"] == "Dr. Vega"
    assert body["start_time"] == "09:00"

    fetched = client.get(f"/sessions/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["room_label"] == "Notes Room"

    listed = client.get("/sessions").get_json()
    assert any(item["id"] == body["id"] for item in listed)


def test_invalid_time_is_400(client):
    response = client.post("/sessions", json=_payload("Notes Room", start="25:00"))
    assert response.status_code == 400


def test_missing_session_is_404(client):
    response = client.get("/sessions/999999")
    assert response.status_code == 404


def test_overlapping_room_is_409(client):
    assert client.post("/sessions", json=_payload("Clash Room")).status_code == 201
    clash = client.post("/sessions", json=_payload("Clash Room", start="11:00", end="13:00", clinician="Dr. Nadal"))
    assert clash.status_code == 409
    assert "room conflict" in clash.get_json()["error"]


def test_migration_does_not_run_twice(operations_database):
    from app.db import connect

    connection = connect()
    try:
        again = apply_migrations(connection)
        assert again == []
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM dbo.schema_migrations WHERE id = %s", ("001_sessions.sql",))
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM dbo.schema_migrations WHERE id = %s", ("002_bookings.sql",))
        assert cursor.fetchone()[0] == 1
    finally:
        connection.close()


def _booking(session_id, **overrides):
    body = {
        "session_id": session_id,
        "start_time": "09:00",
        "patient_ref": "P-2001",
        "procedure_code": "GASTRO",
        "priority": 1,
        "ready": True,
        "available_from": "2099-01-01T00:00:00",
        "available_to": "2099-01-02T00:00:00",
        "minimum_notice_minutes": 0,
        "requested_at": "2099-01-01T08:00:00",
    }
    body.update(overrides)
    return body


def test_create_booking_for_an_existing_session(client):
    session = client.post("/sessions", json=_payload("Booking Room", end="13:00")).get_json()
    created = client.post("/bookings", json=_booking(session["id"]))
    assert created.status_code == 201
    body = created.get_json()
    assert body["session_id"] == session["id"]
    assert body["patient_ref"] == "P-2001"
    assert body["procedure_code"] == "GASTRO"
    assert body["start_time"] == "09:00"
    assert body["end_time"] == "09:30"
    assert body["planning_block_minutes"] == 30
    assert body["room_turnover_minutes"] == 10
    assert body["status"] == "active"
    assert body["timing_source"] == "profile"


def test_colonoscopy_uses_the_45_minute_catalogue(client):
    session = client.post("/sessions", json=_payload("Colon Room", end="13:00")).get_json()
    created = client.post("/bookings", json=_booking(session["id"], procedure_code="COLONO", patient_ref="P-2002"))
    assert created.status_code == 201
    body = created.get_json()
    assert body["end_time"] == "09:45"
    assert body["planning_block_minutes"] == 45
    assert body["room_turnover_minutes"] == 15
    assert body["timing_source"] == "catalogue"


def test_booking_rejects_bad_input_missing_session_and_overlap(client):
    missing = client.post("/bookings", json={})
    assert missing.status_code == 400
    assert "missing field" in missing.get_json()["error"]

    unknown = client.post("/bookings", json=_booking(999999))
    assert unknown.status_code == 404

    session = client.post("/sessions", json=_payload("Overlap Room", end="13:00")).get_json()
    bad_time = client.post("/bookings", json=_booking(session["id"], start_time="25:00"))
    assert bad_time.status_code == 400

    not_ready = client.post("/bookings", json=_booking(session["id"], ready=False, patient_ref="P-2003"))
    assert not_ready.status_code == 400
    assert "not_ready" in not_ready.get_json()["error"]

    short = client.post(
        "/sessions", json=_payload("Short Room", end="09:20", clinician="Dr. Nadal")
    ).get_json()
    unfit = client.post("/bookings", json=_booking(short["id"], patient_ref="P-2004"))
    assert unfit.status_code == 400
    assert "does not fit" in unfit.get_json()["error"]

    assert client.post("/bookings", json=_booking(session["id"], patient_ref="P-2005")).status_code == 201
    clash = client.post("/bookings", json=_booking(session["id"], patient_ref="P-2006", start_time="09:30"))
    assert clash.status_code == 409
    assert "overlaps booking" in clash.get_json()["error"]


def test_booking_survives_a_second_migration(client):
    from app.db import connect

    session = client.post("/sessions", json=_payload("Kept Room", end="13:00")).get_json()
    created = client.post("/bookings", json=_booking(session["id"], patient_ref="P-2007"))
    assert created.status_code == 201
    booking_id = created.get_json()["id"]

    connection = connect()
    try:
        assert apply_migrations(connection) == []
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM dbo.sessions WHERE id = %s", (session["id"],))
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM dbo.bookings WHERE id = %s", (booking_id,))
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM dbo.schema_migrations")
        assert cursor.fetchone()[0] == 2
    finally:
        connection.close()
