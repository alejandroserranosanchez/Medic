"""Foundation check: same DATA_DIR keeps rows across app restart."""

from __future__ import annotations

from clinic import create_app
from clinic.db import get_db
from clinic.operations import repository as ops_repo


def test_session_persists_across_restart(tmp_path):
    data_dir = tmp_path / "clinic-data"

    app1 = create_app({"TESTING": True, "DATA_DIR": str(data_dir)})
    with app1.app_context():
        db = get_db()
        session_id = ops_repo.create_session(
            db,
            room_label="Room Persist",
            clinician_label="Dr. Persist",
            session_date="2026-10-11",
            start_time="08:00",
            end_time="11:00",
        )

    # New app instance, same DATA_DIR — simulates process restart.
    app2 = create_app({"TESTING": True, "DATA_DIR": str(data_dir)})
    with app2.app_context():
        db = get_db()
        rows = ops_repo.list_sessions(db)
        assert any(row["id"] == session_id and row["room_label"] == "Room Persist" for row in rows)


def test_seed_runs_once_only(tmp_path):
    data_dir = tmp_path / "seed-once"
    app1 = create_app({"TESTING": True, "DATA_DIR": str(data_dir)})
    with app1.app_context():
        db = get_db()
        before = db.execute("SELECT COUNT(*) AS n FROM procedure_types").fetchone()["n"]
        assert before == 2

    app2 = create_app({"TESTING": True, "DATA_DIR": str(data_dir)})
    with app2.app_context():
        db = get_db()
        after = db.execute("SELECT COUNT(*) AS n FROM procedure_types").fetchone()["n"]
        assert after == before
