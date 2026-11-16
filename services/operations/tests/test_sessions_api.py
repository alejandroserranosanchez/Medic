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
    connection.cursor().execute("DELETE FROM dbo.sessions")
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
    finally:
        connection.close()
