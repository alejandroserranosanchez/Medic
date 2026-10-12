"""Flask application factory for Medic."""

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
        DEMO_NOW=os.environ.get("DEMO_NOW"),  # optional ISO local datetime for demos/tests
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
    from clinic.finance.routes import bp as finance_bp

    app.register_blueprint(operations_bp)
    app.register_blueprint(finance_bp)

    app.add_template_filter(_nice_date, "nice_date")
    app.add_template_filter(_nice_datetime, "nice_datetime")
    app.add_template_filter(_eur, "eur")

    @app.context_processor
    def inject_clock():
        from clinic.clock import now as clock_now

        return {"clock_now": clock_now(), "demo_clock": bool(app.config.get("DEMO_NOW"))}

    @app.route("/")
    def overview():
        from flask import render_template

        from clinic.clock import now as clock_now
        from clinic.db import get_db
        from clinic.finance import repository as finance_repo
        from clinic.operations import repository as ops_repo
        from clinic.operations.routes import with_timeline

        db = get_db()
        now = clock_now()
        today = now.date().isoformat()
        receivables = finance_repo.list_receivables(db, as_of_date=today)
        schedule = with_timeline(ops_repo.list_schedule(db), now)

        upcoming = [i for i in schedule if i["session"]["session_date"] >= today]
        preview = upcoming[0] if upcoming else (schedule[-1] if schedule else None)
        first_gap = None
        if preview and preview["gaps"] and preview["session"]["session_date"] >= today:
            gap_start, gap_end = preview["gaps"][0]
            candidates = ops_repo.slot_candidates(
                db, session_id=preview["session"]["id"], start_time=gap_start, now=now
            )
            first_gap = {
                "start": gap_start,
                "end": gap_end,
                "eligible": sum(1 for c in candidates if not c["issues"]),
            }

        to_complete = sum(
            1
            for item in schedule
            for b in item["bookings"]
            if b["status"] == "active" and item["completable"][b["id"]]
        )
        counts = {
            "scheduled": sum(
                1
                for item in schedule
                for b in item["bookings"]
                if b["status"] == "active" and not item["completable"][b["id"]]
            ),
            "to_complete": to_complete,
            "waiting_requests": ops_repo.count_waiting_requests(db),
            "open_receivables": sum(1 for r in receivables if r["balance"].balance_cents > 0),
            "outstanding_cents": sum(max(r["balance"].balance_cents, 0) for r in receivables),
            "overdue": sum(1 for r in receivables if r["balance"].overdue),
        }
        procedures = {p["code"]: p["display_name"] for p in ops_repo.list_procedure_types(db)}
        return render_template(
            "overview.html",
            counts=counts,
            preview=preview,
            first_gap=first_gap,
            receivable_by_booking={r["source_booking_id"]: r for r in receivables},
            procedure_names=procedures,
        )

    return app


def _nice_date(value: str) -> str:
    """'2026-10-10' -> 'Sat 10 Oct 2026'."""
    from datetime import date

    try:
        return date.fromisoformat(str(value)[:10]).strftime("%a %d %b %Y")
    except ValueError:
        return str(value)


def _nice_datetime(value: str) -> str:
    """'2026-10-10T09:00:00' -> '10 Oct, 09:00'."""
    from clinic.timeutil import parse_datetime_local

    try:
        return parse_datetime_local(str(value)).strftime("%d %b, %H:%M")
    except ValueError:
        return str(value)


def _eur(cents: int) -> str:
    """Integer cents -> '€11,400.00' (display only)."""
    sign = "−" if cents < 0 else ""
    whole, frac = divmod(abs(int(cents)), 100)
    return f"{sign}€{whole:,}.{frac:02d}"
