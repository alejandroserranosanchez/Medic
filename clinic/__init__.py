"""Flask application factory for CareQuanta."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)

    project_root = Path(__file__).resolve().parent.parent
    default_data = project_root / "data"

    app.config.from_mapping(
        APP_NAME=os.environ.get("APP_NAME", "Medic"),
        SECRET_KEY=os.environ.get("SECRET_KEY", "medic-dev-only"),
        HOST="0.0.0.0",
        PORT=int(os.environ.get("PORT", "8000")),
        DATA_DIR=os.environ.get("DATA_DIR", str(default_data)),
        DB_FILENAME="clinic.sqlite3",
    )

    if test_config:
        app.config.update(test_config)

    from clinic.db import close_db, init_db
    from clinic.seed import seed_if_empty

    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db()
        seed_if_empty()

    from clinic.operations.routes import bp as operations_bp

    app.register_blueprint(operations_bp)

    @app.route("/")
    def overview():
        from flask import render_template

        from clinic.db import get_db

        db = get_db()
        counts = {
            "sessions": db.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"],
            "bookings_active": db.execute(
                "SELECT COUNT(*) AS n FROM bookings WHERE status = 'active'"
            ).fetchone()["n"],
            "requests": db.execute("SELECT COUNT(*) AS n FROM requests").fetchone()["n"],
        }
        return render_template("overview.html", counts=counts)

    return app
