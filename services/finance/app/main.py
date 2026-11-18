"""Finance service scaffold.

This process can answer a health check against its own database.
It does not create receivables, record payments, or compare equipment yet.
"""

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
