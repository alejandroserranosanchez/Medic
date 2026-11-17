"""Operations service.

GET /health checks this service's own database.
Sessions can be listed, fetched, and created.
POST /bookings saves one procedure inside an existing session.
"""

from __future__ import annotations

import os
from datetime import datetime

import pymssql
from flask import Flask, jsonify, request

from app.bookings import create_booking
from app.db import connect
from app.rules import OperationsError
from app.sessions import create_session, get_session, list_sessions


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

    @app.get("/sessions")
    def sessions_list():
        with connect() as conn:
            return jsonify(list_sessions(conn))

    @app.get("/sessions/<int:session_id>")
    def sessions_get(session_id: int):
        try:
            with connect() as conn:
                return jsonify(get_session(conn, session_id))
        except OperationsError as exc:
            return jsonify({"error": exc.reason}), exc.status

    @app.post("/sessions")
    def sessions_create():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "JSON object required"}), 400
        try:
            fields = {
                "room_label": body["room_label"],
                "session_date": body["session_date"],
                "start_time": body["start_time"],
                "end_time": body["end_time"],
                "clinician_id": body.get("clinician_id"),
                "clinician_label": body.get("clinician_label"),
            }
        except KeyError as exc:
            return jsonify({"error": f"missing field {exc.args[0]}"}), 400
        try:
            with connect() as conn:
                created = create_session(conn, **fields)
        except (OperationsError, ValueError) as exc:
            status = getattr(exc, "status", 400)
            reason = getattr(exc, "reason", str(exc))
            return jsonify({"error": reason}), status
        return jsonify(created), 201

    @app.post("/bookings")
    def bookings_create():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "JSON object required"}), 400
        try:
            fields = {
                "session_id": body["session_id"],
                "start_time": body["start_time"],
                "patient_ref": body["patient_ref"],
                "procedure_code": body["procedure_code"],
                "priority": body["priority"],
                "ready": body["ready"],
                "available_from": body["available_from"],
                "available_to": body["available_to"],
                "minimum_notice_minutes": body["minimum_notice_minutes"],
                "requested_at": body.get("requested_at")
                or datetime.now().replace(microsecond=0).isoformat(timespec="seconds"),
            }
        except KeyError as exc:
            return jsonify({"error": f"missing field {exc.args[0]}"}), 400
        try:
            with connect() as conn:
                created = create_booking(conn, **fields)
        except (OperationsError, ValueError) as exc:
            status = getattr(exc, "status", 400)
            reason = getattr(exc, "reason", str(exc))
            return jsonify({"error": reason}), status
        return jsonify(created), 201

    return app


app = create_app()


def main() -> None:
    from app.migrate import apply_migrations
    from app.seed import seed_catalogue, seed_clinicians

    apply_migrations()
    seed_clinicians()
    seed_catalogue()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)


if __name__ == "__main__":
    main()
