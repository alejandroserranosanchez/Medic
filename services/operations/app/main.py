"""Operations service scaffold.

This process can answer a health check against its own database.
It does not schedule sessions, bookings, or waiting requests yet.
"""

import pymssql
from flask import Flask, jsonify

from app.db import connect


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        """Report only this service. Finance being down does not change this answer."""
        try:
            with connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except (pymssql.Error, KeyError):
            return jsonify({"status": "unavailable"}), 503
        return jsonify({"status": "ok"})

    return app


app = create_app()
