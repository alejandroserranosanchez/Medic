"""Finance migrations. The runner tests use a fake connection. The rest need SQL Server."""

from __future__ import annotations

from pathlib import Path

import pymssql
import pytest

from app.migrate import apply_migrations, split_batches

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"

ALL_MIGRATIONS = [
    "001_receivables.sql",
    "002_payments.sql",
    "003_fee_assumptions.sql",
    "004_receivable_currency.sql",
]


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
    assert "currency_code" in lowered
    assert "df_receivables_currency_code" in lowered
    assert "ck_receivables_currency_code" in lowered


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


def test_runner_applies_each_file_once(capsys):
    connection = _Connection()
    first = apply_migrations(connection)
    second = apply_migrations(connection)
    assert first == ALL_MIGRATIONS
    assert second == []
    assert connection.applied == ALL_MIGRATIONS
    logged = capsys.readouterr().out
    for name in ALL_MIGRATIONS:
        assert f"Applied migration: {name}" in logged
    assert logged.count("Applied migration:") == 4


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


def _ensure_schema_migrations(cursor, connection):
    cursor.execute(
        """
        IF OBJECT_ID(N'dbo.schema_migrations', N'U') IS NULL
        CREATE TABLE dbo.schema_migrations (
            id NVARCHAR(200) NOT NULL PRIMARY KEY,
            applied_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
        )
        """
    )
    connection.commit()


def _apply_sql_files(connection, names: list[str]) -> None:
    cursor = connection.cursor()
    _ensure_schema_migrations(cursor, connection)
    for name in names:
        path = MIGRATIONS / name
        for batch in split_batches(path.read_text(encoding="utf-8")):
            cursor.execute(batch)
        cursor.execute("INSERT INTO dbo.schema_migrations (id) VALUES (%s)", (name,))
        connection.commit()


def test_saved_money_survives_reconnect_and_a_second_migration(finance_database):
    from app.db import connect

    assert apply_migrations() == ALL_MIGRATIONS
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
            """
            SELECT source_booking_id, expected_fee_cents, currency_code
            FROM dbo.receivables WHERE id = %s
            """,
            (receivable_id,),
        )
        assert cursor.fetchone() == (41, 12000, "EUR")
        cursor.execute(
            "SELECT amount_cents FROM dbo.payments WHERE receivable_id = %s",
            (receivable_id,),
        )
        assert cursor.fetchone() == (9000,)
        cursor.execute("SELECT COUNT(*) FROM dbo.schema_migrations")
        assert cursor.fetchone()[0] == 4
    finally:
        second.close()


def test_currency_migration_preserves_populated_receivable_and_payment(finance_database, capsys):
    """§4 style: change a populated table in place; rows and payments stay."""
    from app.db import connect

    connection = connect()
    try:
        _apply_sql_files(
            connection,
            ["001_receivables.sql", "002_payments.sql", "003_fee_assumptions.sql"],
        )
        cursor = connection.cursor()
        receivable_id = _insert_receivable(cursor, booking_id=77)
        cursor.execute(
            """
            INSERT INTO dbo.payments (receivable_id, payment_reference, amount_cents, paid_date)
            VALUES (%s, N'PAY-CURRENCY', 4500, '2026-11-21')
            """,
            (receivable_id,),
        )
        connection.commit()
        cursor.execute(
            """
            SELECT id, source_booking_id, procedure_code, performed_date, due_date, expected_fee_cents
            FROM dbo.receivables WHERE id = %s
            """,
            (receivable_id,),
        )
        before = cursor.fetchone()
        # pymssql may return date objects for DATE columns
        assert before[0] == receivable_id
        assert before[1] == 77
        assert str(before[2]).strip() == "GASTRO"
        assert str(before[3])[:10] == "2026-11-20"
        assert str(before[4])[:10] == "2026-12-20"
        assert before[5] == 12000
        cursor.execute(
            """
            SELECT payment_reference, amount_cents, paid_date
            FROM dbo.payments WHERE receivable_id = %s
            """,
            (receivable_id,),
        )
        payment_before = cursor.fetchone()
        assert str(payment_before[0]).strip() == "PAY-CURRENCY"
        assert payment_before[1] == 4500
        assert str(payment_before[2])[:10] == "2026-11-21"
    finally:
        connection.close()

    applied = apply_migrations()
    assert applied == ["004_receivable_currency.sql"]
    assert "Applied migration: 004_receivable_currency.sql" in capsys.readouterr().out

    after = connect()
    try:
        cursor = after.cursor()
        cursor.execute(
            """
            SELECT id, source_booking_id, procedure_code, performed_date, due_date,
                   expected_fee_cents, currency_code
            FROM dbo.receivables WHERE id = %s
            """,
            (receivable_id,),
        )
        row = cursor.fetchone()
        assert row[0] == receivable_id
        assert row[1] == 77
        assert str(row[2]).strip() == "GASTRO"
        assert str(row[3])[:10] == "2026-11-20"
        assert str(row[4])[:10] == "2026-12-20"
        assert row[5] == 12000
        assert str(row[6]).strip() == "EUR"

        cursor.execute(
            """
            SELECT payment_reference, amount_cents, paid_date
            FROM dbo.payments WHERE receivable_id = %s
            """,
            (receivable_id,),
        )
        payment_after = cursor.fetchone()
        assert str(payment_after[0]).strip() == "PAY-CURRENCY"
        assert payment_after[1] == 4500
        assert str(payment_after[2])[:10] == "2026-11-21"

        new_id = _insert_receivable(cursor, booking_id=88)
        after.commit()
        cursor.execute(
            "SELECT currency_code, expected_fee_cents FROM dbo.receivables WHERE id = %s",
            (new_id,),
        )
        currency, fee = cursor.fetchone()
        assert str(currency).strip() == "EUR"
        assert fee == 12000

        with pytest.raises(pymssql.IntegrityError):
            cursor.execute(
                """
                INSERT INTO dbo.receivables (
                    source_booking_id, procedure_code, performed_date, due_date,
                    expected_fee_cents, currency_code
                ) VALUES (89, N'GASTRO', '2026-11-20', '2026-12-20', 12000, 'USD')
                """
            )
        after.rollback()

        assert apply_migrations(after) == []
        cursor.execute(
            "SELECT COUNT(*) FROM dbo.schema_migrations WHERE id = %s",
            ("004_receivable_currency.sql",),
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM dbo.schema_migrations")
        assert cursor.fetchone()[0] == 4
    finally:
        after.close()


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
