"""Finance migrations. The runner tests use a fake connection. The rest need SQL Server."""

from __future__ import annotations

from pathlib import Path

import pymssql
import pytest

from app.migrate import apply_migrations, split_batches

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


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
    assert first == ["001_receivables.sql", "002_payments.sql", "003_fee_assumptions.sql"]
    assert second == []
    assert connection.applied == ["001_receivables.sql", "002_payments.sql", "003_fee_assumptions.sql"]


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

    assert apply_migrations() == ["001_receivables.sql", "002_payments.sql", "003_fee_assumptions.sql"]
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
        assert cursor.fetchone()[0] == 3
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
