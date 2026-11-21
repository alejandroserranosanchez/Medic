"""Finance migrations. The runner tests use a fake connection. The rest need SQL Server."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pymssql
import pytest

from app.migrate import apply_migrations, split_batches

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
ROOT = Path(__file__).resolve().parents[3]


def test_go_on_its_own_line_splits_batches():
    assert split_batches("SELECT 1\nGO\n\nGO\nSELECT 2\n") == ["SELECT 1", "SELECT 2"]


def test_sql_files_keep_the_booking_reference_inside_finance():
    text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(MIGRATIONS.glob("*.sql")))
    lowered = text.lower()
    assert "references dbo.receivables" in lowered
    assert "references dbo.bookings" not in lowered
    assert "operations.dbo" not in lowered
    assert "expected_fee_cents" in lowered
    assert "amount_cents" in lowered


class _Cursor:
    def __init__(self, applied: list[str]):
        self.applied = applied
        self.row = None

    def execute(self, statement, params=None):
        compact = " ".join(statement.split())
        if compact.startswith("SELECT 1 FROM dbo.schema_migrations"):
            self.row = (1,) if params[0] in self.applied else None
            return
        if compact.startswith("INSERT INTO dbo.schema_migrations"):
            self.applied.append(params[0])
        self.row = None

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self):
        self.applied: list[str] = []
        self.cursor_obj = _Cursor(self.applied)

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        return None

    def close(self):
        return None


def test_runner_applies_each_file_once():
    connection = _Connection()
    first = apply_migrations(connection)
    second = apply_migrations(connection)
    assert first == ["001_receivables.sql", "002_payments.sql"]
    assert second == []
    assert connection.applied == ["001_receivables.sql", "002_payments.sql"]


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


def _insert_receivable(cursor, booking_id=41):
    cursor.execute(
        """
        INSERT INTO dbo.receivables (
            source_booking_id, procedure_code, performed_date, due_date, expected_fee_cents
        )
        OUTPUT INSERTED.id
        VALUES (%s, N'GASTRO', '2026-11-20', '2026-12-20', 12000)
        """,
        (booking_id,),
    )
    return cursor.fetchone()[0]


def test_saved_money_survives_reconnect_and_a_second_migration(finance_database):
    from app.db import connect

    assert apply_migrations() == ["001_receivables.sql", "002_payments.sql"]
    first = connect()
    try:
        cursor = first.cursor()
        receivable_id = _insert_receivable(cursor)
        cursor.execute(
            """
            INSERT INTO dbo.payments (receivable_id, payment_reference, amount_cents, paid_date)
            VALUES (%s, N'PAY-9000', 9000, '2026-11-21')
            """,
            (receivable_id,),
        )
        first.commit()
    finally:
        first.close()

    second = connect()
    try:
        assert apply_migrations(second) == []
        cursor = second.cursor()
        cursor.execute(
            "SELECT source_booking_id, expected_fee_cents FROM dbo.receivables WHERE id = %s",
            (receivable_id,),
        )
        assert cursor.fetchone() == (41, 12000)
        cursor.execute(
            "SELECT amount_cents FROM dbo.payments WHERE receivable_id = %s",
            (receivable_id,),
        )
        assert cursor.fetchone() == (9000,)
        cursor.execute("SELECT COUNT(*) FROM dbo.schema_migrations")
        assert cursor.fetchone()[0] == 2
    finally:
        second.close()


def test_money_rules_are_rejected_by_the_database(finance_database):
    from app.db import connect

    apply_migrations()
    connection = connect()
    try:
        cursor = connection.cursor()
        receivable_id = _insert_receivable(cursor)
        connection.commit()

        with pytest.raises(pymssql.IntegrityError):
            _insert_receivable(cursor, booking_id=41)
        connection.rollback()

        with pytest.raises(pymssql.IntegrityError):
            cursor.execute(
                """
                INSERT INTO dbo.receivables (
                    source_booking_id, procedure_code, performed_date, due_date, expected_fee_cents
                ) VALUES (42, N'GASTRO', '2026-11-20', '2026-11-19', 12000)
                """
            )
        connection.rollback()

        with pytest.raises(pymssql.IntegrityError):
            cursor.execute(
                """
                INSERT INTO dbo.receivables (
                    source_booking_id, procedure_code, performed_date, due_date, expected_fee_cents
                ) VALUES (43, N'GASTRO', '2026-11-20', '2026-12-20', -1)
                """
            )
        connection.rollback()

        with pytest.raises(pymssql.IntegrityError):
            cursor.execute(
                """
                INSERT INTO dbo.payments (receivable_id, payment_reference, amount_cents, paid_date)
                VALUES (999999, N'PAY-MISSING', 100, '2026-11-21')
                """
            )
        connection.rollback()

        cursor.execute(
            """
            INSERT INTO dbo.payments (receivable_id, payment_reference, amount_cents, paid_date)
            VALUES (%s, N'PAY-SAME', 100, '2026-11-21')
            """,
            (receivable_id,),
        )
        connection.commit()
        with pytest.raises(pymssql.IntegrityError):
            cursor.execute(
                """
                INSERT INTO dbo.payments (receivable_id, payment_reference, amount_cents, paid_date)
                VALUES (%s, N'PAY-SAME', 200, '2026-11-22')
                """,
                (receivable_id,),
            )
        connection.rollback()

        with pytest.raises(pymssql.IntegrityError):
            cursor.execute(
                """
                INSERT INTO dbo.payments (receivable_id, payment_reference, amount_cents, paid_date)
                VALUES (%s, N'PAY-ZERO', 0, '2026-11-21')
                """,
                (receivable_id,),
            )
        connection.rollback()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM sys.foreign_key_columns AS link
            JOIN sys.columns AS column_info
              ON column_info.object_id = link.parent_object_id
             AND column_info.column_id = link.parent_column_id
            JOIN sys.tables AS table_info ON table_info.object_id = column_info.object_id
            WHERE table_info.name = N'receivables'
              AND column_info.name = N'source_booking_id'
            """
        )
        assert cursor.fetchone()[0] == 0
    finally:
        connection.close()
