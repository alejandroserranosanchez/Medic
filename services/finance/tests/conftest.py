"""Shared Finance test database. Skips when local SQL Server is not reachable."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pymssql
import pytest

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
def finance_database():
    values = _env_file()
    password = (
        os.environ.get("FINANCE_DB_PASSWORD")
        or values.get("FINANCE_DB_PASSWORD")
        or "FinanceTestOnly1"
    )
    host = os.environ.get("SQL_HOST", "127.0.0.1")
    port = int(os.environ.get("SQL_PORT") or values.get("SQL_PORT") or "1433")
    admin = _sa_connection()
    cursor = admin.cursor()
    cursor.execute(
        """
        IF DB_ID(N'finance_test') IS NOT NULL
        BEGIN
            ALTER DATABASE finance_test SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
            DROP DATABASE finance_test;
        END
        """
    )
    cursor.execute("CREATE DATABASE finance_test")
    cursor.execute(
        """
        IF SUSER_ID(N'finance_test_user') IS NULL
            CREATE LOGIN finance_test_user WITH PASSWORD = %s, CHECK_POLICY = OFF
        ELSE
            ALTER LOGIN finance_test_user WITH PASSWORD = %s
        """,
        (password, password),
    )
    admin.close()
    owner = pymssql.connect(
        server=host,
        port=port,
        user="sa",
        password=os.environ.get("MSSQL_SA_PASSWORD") or values["MSSQL_SA_PASSWORD"],
        database="finance_test",
        login_timeout=3,
        autocommit=True,
    )
    owner.cursor().execute(
        """
        IF USER_ID(N'finance_test_user') IS NULL
            CREATE USER finance_test_user FOR LOGIN finance_test_user
        """
    )
    owner.cursor().execute(
        """
        IF IS_ROLEMEMBER(N'db_owner', N'finance_test_user') <> 1
            ALTER ROLE db_owner ADD MEMBER finance_test_user
        """
    )
    owner.close()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"mssql://finance_test_user:{password}@{host}:{port}/finance_test"
    yield
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous
