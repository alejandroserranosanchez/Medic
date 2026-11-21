"""Finance service.

This process applies its own migrations, then answers a health check.
It does not yet expose receivable or payment endpoints.
"""

from __future__ import annotations

import os

import pymssql
from flask import Flask, jsonify

from app.db import connect


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

    return app


app = create_app()


def main() -> None:
    from app.migrate import apply_migrations

    apply_migrations()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)


if __name__ == "__main__":
    main()
