"""Operations service.

GET /health checks this service's own database.
Sessions can be listed, fetched, and created.
POST /bookings saves one procedure inside an existing session.
POST /bookings/<id>/complete asks Finance to record the receivable.
"""

from __future__ import annotations

import os
from datetime import datetime

import pymssql
from flask import Flask, jsonify, request

from app.bookings import create_booking
from app.completion import complete_booking
from app.cors import apply_cors
from app.db import connect
from app.rules import OperationsError
from app.sessions import create_session, get_session, list_sessions


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
    apply_cors(app)

    @app.get("/health")
    def health():
        """Report only this service. Finance being down does not change this answer."""
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

    @app.post("/bookings/<int:booking_id>/complete")
    def bookings_complete(booking_id: int):
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "JSON object required"}), 400
        try:
            performed_date = body["performed_date"]
            due_date = body["due_date"]
        except KeyError as exc:
            return jsonify({"error": f"missing field {exc.args[0]}"}), 400
        try:
            with connect() as conn:
                status, payload = complete_booking(
                    conn,
                    booking_id=booking_id,
                    performed_date=performed_date,
                    due_date=due_date,
                )
        except (OperationsError, ValueError) as exc:
            code = getattr(exc, "status", 400)
            reason = getattr(exc, "reason", str(exc))
            return jsonify({"error": reason}), code
        return jsonify(payload), status

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
