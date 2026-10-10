"""Finance persistence only. Does not import operations modules."""

from __future__ import annotations

import json
import sqlite3

from clinic.finance.investment import (
    ScenarioInputs,
    compare_scenario,
    inputs_to_dict,
    result_to_dict,
)
from clinic.finance.reconciliation import classify_balance


class FinanceError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def get_fee_cents(db: sqlite3.Connection, procedure_code: str) -> int:
    row = db.execute(
        "SELECT expected_fee_cents FROM fee_assumptions WHERE procedure_code = ?",
        (procedure_code,),
    ).fetchone()
    if row is None:
        raise FinanceError(f"no fee assumption for {procedure_code}")
    return int(row["expected_fee_cents"])


def insert_receivable(
    db: sqlite3.Connection,
    *,
    source_booking_id: int,
    procedure_code: str,
    performed_date: str,
    due_date: str,
    expected_fee_cents: int,
) -> int:
    """Insert only — caller owns the transaction (no commit here)."""
    existing = db.execute(
        "SELECT id FROM receivables WHERE source_booking_id = ?",
        (source_booking_id,),
    ).fetchone()
    if existing is not None:
        raise FinanceError("receivable already exists for this booking")

    cur = db.execute(
        """
        INSERT INTO receivables (
            source_booking_id, procedure_code, performed_date, due_date, expected_fee_cents
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (source_booking_id, procedure_code, performed_date, due_date, expected_fee_cents),
    )
    return int(cur.lastrowid)


def list_receivables(db: sqlite3.Connection, as_of_date: str) -> list[dict]:
    rows = db.execute(
        """
        SELECT r.*,
               COALESCE((
                   SELECT SUM(p.amount_cents) FROM payments p WHERE p.receivable_id = r.id
               ), 0) AS paid_cents
        FROM receivables r
        ORDER BY r.id
        """
    ).fetchall()
    out: list[dict] = []
    for row in rows:
        view = classify_balance(
            expected_fee_cents=int(row["expected_fee_cents"]),
            paid_cents=int(row["paid_cents"]),
            due_date=row["due_date"],
            as_of_date=as_of_date,
        )
        out.append({**dict(row), "balance": view})
    return out


def record_payment(
    db: sqlite3.Connection,
    *,
    receivable_id: int,
    payment_reference: str,
    amount_cents: int,
    paid_date: str,
) -> int:
    if amount_cents <= 0:
        raise FinanceError("payment amount must be positive cents")
    ref = payment_reference.strip()
    if not ref:
        raise FinanceError("payment reference required")

    recv = db.execute(
        "SELECT id FROM receivables WHERE id = ?",
        (receivable_id,),
    ).fetchone()
    if recv is None:
        raise FinanceError("receivable not found")

    existing = db.execute(
        "SELECT id, receivable_id, amount_cents, paid_date FROM payments WHERE payment_reference = ?",
        (ref,),
    ).fetchone()
    if existing is not None:
        if (
            int(existing["receivable_id"]) == receivable_id
            and int(existing["amount_cents"]) == amount_cents
            and existing["paid_date"] == paid_date
        ):
            return int(existing["id"])  # idempotent duplicate
        raise FinanceError("payment reference already used with different details")

    db.execute("BEGIN IMMEDIATE")
    try:
        cur = db.execute(
            """
            INSERT INTO payments (receivable_id, payment_reference, amount_cents, paid_date)
            VALUES (?, ?, ?, ?)
            """,
            (receivable_id, ref, amount_cents, paid_date),
        )
        db.execute("COMMIT")
        return int(cur.lastrowid)
    except sqlite3.IntegrityError as exc:
        db.execute("ROLLBACK")
        raise FinanceError(f"could not record payment: {exc}") from exc
    except Exception:
        db.execute("ROLLBACK")
        raise


def save_investment_scenario(
    db: sqlite3.Connection,
    *,
    inputs: ScenarioInputs,
    created_at: str,
) -> int:
    """Compute, then persist input+output snapshots. Future fee edits cannot rewrite them."""
    result = compare_scenario(inputs)
    db.execute("BEGIN IMMEDIATE")
    try:
        cur = db.execute(
            """
            INSERT INTO investment_scenarios (
                name, procedure_code, created_at, model_version,
                input_snapshot_json, output_snapshot_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                inputs.name.strip(),
                inputs.procedure_code.strip(),
                created_at,
                result.model_version,
                json.dumps(inputs_to_dict(inputs), sort_keys=True),
                json.dumps(result_to_dict(result), sort_keys=True),
            ),
        )
        db.execute("COMMIT")
        return int(cur.lastrowid)
    except Exception:
        db.execute("ROLLBACK")
        raise


def list_investment_scenarios(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        """
        SELECT id, name, procedure_code, created_at, model_version
        FROM investment_scenarios
        ORDER BY id DESC
        """
    ).fetchall()


def get_investment_scenario(db: sqlite3.Connection, scenario_id: int) -> dict:
    row = db.execute(
        "SELECT * FROM investment_scenarios WHERE id = ?",
        (scenario_id,),
    ).fetchone()
    if row is None:
        raise FinanceError("scenario not found")
    return {
        "id": row["id"],
        "name": row["name"],
        "procedure_code": row["procedure_code"],
        "created_at": row["created_at"],
        "model_version": row["model_version"],
        "inputs": json.loads(row["input_snapshot_json"]),
        "outputs": json.loads(row["output_snapshot_json"]),
    }
