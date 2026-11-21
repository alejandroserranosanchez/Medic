"""Finance service.

This process applies its own migrations, then answers health, receivables, and payments.
It does not ask Operations whether a booking exists.
"""

from __future__ import annotations

import os

import pymssql
from flask import Flask, jsonify, request

from app.db import connect
from app.receivables import FinanceError, create_receivable, get_balance, get_receivable, record_payment


def database_accepts_a_write() -> bool:
    """Read and write this service's own database. Another service is not contacted."""
    with connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            IF OBJECT_ID(N'dbo.health_checks', N'U') IS NULL
            CREATE TABLE dbo.health_checks (
                id INT NOT NULL PRIMARY KEY,
                touched_at DATETIME2 NOT NULL
            )
            """
        )
        cursor.execute("UPDATE dbo.health_checks SET touched_at = SYSUTCDATETIME() WHERE id = 1")
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO dbo.health_checks (id, touched_at) VALUES (1, SYSUTCDATETIME())"
            )
        cursor.execute("SELECT id FROM dbo.health_checks WHERE id = 1")
        row = cursor.fetchone()
        conn.commit()
    return row is not None


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        """Report only this service. Operations being down does not change this answer."""
        try:
            writable = database_accepts_a_write()
        except (pymssql.Error, KeyError):
            return jsonify({"status": "unavailable"}), 503
        if not writable:
            return jsonify({"status": "unavailable"}), 503
        return jsonify(
            {
                "status": "ok",
                "db": "ok",
                "version": os.environ.get("GIT_SHA", "unknown"),
            }
        )

    @app.post("/receivables")
    def receivables_create():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "JSON object required"}), 400
        try:
            fields = {
                "source_booking_id": body["source_booking_id"],
                "procedure_code": body["procedure_code"],
                "performed_date": body["performed_date"],
                "due_date": body["due_date"],
                "expected_fee_cents": body["expected_fee_cents"],
            }
        except KeyError as exc:
            return jsonify({"error": f"missing field {exc.args[0]}"}), 400
        try:
            with connect() as conn:
                created = create_receivable(conn, **fields)
        except (FinanceError, ValueError) as exc:
            return jsonify({"error": getattr(exc, "reason", str(exc))}), getattr(exc, "status", 400)
        return jsonify(created), 201

    @app.get("/receivables/<int:receivable_id>")
    def receivables_get(receivable_id: int):
        try:
            with connect() as conn:
                return jsonify(get_receivable(conn, receivable_id))
        except FinanceError as exc:
            return jsonify({"error": exc.reason}), exc.status

    @app.post("/receivables/<int:receivable_id>/payments")
    def payments_create(receivable_id: int):
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "JSON object required"}), 400
        try:
            fields = {
                "receivable_id": receivable_id,
                "payment_reference": body["payment_reference"],
                "amount_cents": body["amount_cents"],
                "paid_date": body["paid_date"],
            }
        except KeyError as exc:
            return jsonify({"error": f"missing field {exc.args[0]}"}), 400
        try:
            with connect() as conn:
                payment, created = record_payment(conn, **fields)
        except (FinanceError, ValueError) as exc:
            return jsonify({"error": getattr(exc, "reason", str(exc))}), getattr(exc, "status", 400)
        return jsonify(payment), 201 if created else 200

    @app.get("/receivables/<int:receivable_id>/balance")
    def receivables_balance(receivable_id: int):
        try:
            with connect() as conn:
                return jsonify(get_balance(conn, receivable_id, request.args.get("as_of")))
        except (FinanceError, ValueError) as exc:
            return jsonify({"error": getattr(exc, "reason", str(exc))}), getattr(exc, "status", 400)

    return app


app = create_app()


def main() -> None:
    from app.migrate import apply_migrations

    apply_migrations()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)


if __name__ == "__main__":
    main()
