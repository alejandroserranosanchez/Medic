# Medic

Local coursework app for a small private diagnostic clinic: capacity (sessions and bookings without double booking), payment reconciliation, and a simple keep/buy/lease equipment comparison. All data is fictional. The visible name can be overridden with `APP_NAME`.

Full write-up (SDLC, SMART goals, architecture and database diagrams, testing, AI disclosure): [`docs/report.md`](docs/report.md).

## Status (2026-10-12, submission)

Professor use-case approval: **confirmed by student on 2026-10-07**.

Working:

- Overview, Schedule, Collections and Equipment plans screens, all persisted in SQLite
- Booking end time calculated on the server from the clinician + procedure profile (or catalogue default)
- Eligibility checks (ready, availability window, minimum notice) and room/clinician conflict checks
- Complete booking → exactly one receivable (fee snapshot); payments with unpaid/partial/settled/overpaid and a separate overdue flag
- A booking can only be marked as done once it has started, with the booking's own session date as the performed date and a due date that is not earlier
- Keep/buy/lease comparison with save and reopen

- Slot recovery: each session is drawn as a timeline with free gaps; cancelling a booking shows which waiting patients can take the freed slot (ranked by priority, then waiting time) and why the others can't

Suggestions are calculated live and not stored, so the `recovery_proposals` table is still unused. The demo data is seeded relative to the clock: one session for "tomorrow" with free time to fill, and one session from "yesterday" whose booking can be marked as done. If you have an older `data/` folder, delete it (or use a new `DATA_DIR`) to get the current demo data.

## Setup and run

Tested with Python 3.10.0 on macOS.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000` (the server binds `0.0.0.0`). No interactive setup: the schema and fictional seed data are created automatically on first start.

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8000` | HTTP port |
| `DATA_DIR` | `./data` | Directory for the SQLite file |
| `APP_NAME` | `Medic` | Visible product name |
| `SECRET_KEY` | `medic-dev-only` | Flask flash messages |
| `DEMO_NOW` | *(unset = real clock)* | Fixed planning clock, format `YYYY-MM-DDTHH:MM:SS` |

Database path: `DATA_DIR/clinic.sqlite3`. Seed data is inserted only when the database is empty, so restarting never wipes your data.

## Testing and coverage

```bash
python -m pytest
```

Coverage of core business logic (fails if below 70%):

```bash
python -m pytest --cov=clinic.operations --cov=clinic.finance --cov=clinic.application --cov=clinic.timeutil --cov-report=term-missing --cov-fail-under=70
```

Measured on 2026-10-12 (Python 3.10.0, pytest 9.0.2, pytest-cov 7.1.0):

| Scope | Coverage |
|---|---|
| Combined core logic (command above) | 83.65% |
| Operations domain only (`--cov=clinic.operations`) | 83.51% |
| Finance domain only (`--cov=clinic.finance`) | 82.65% |

Result: `53 passed`.

## Layout

- `app.py` — start command
- `clinic/__init__.py` — app factory and configuration from environment
- `clinic/db.py`, `clinic/schema.sql`, `clinic/seed.py` — SQLite connection, schema, migration, fictional seed
- `clinic/operations/` — Operations domain: sessions, requests, bookings (routes / service rules / repository SQL)
- `clinic/finance/` — Finance domain: receivables, payments, investment comparison
- `clinic/application.py` — `complete_booking`, the one action that writes to both domains in a single transaction
- `tests/` — unit, SQLite integration and HTTP tests
- `ADR.md`, `AI_USAGE.md`, `PROJECT_BRIEF.md`, `ACCEPTANCE_CRITERIA.md`, `docs/report.md`

## Assignment notes

- Single process, one SQLite file, one root `requirements.txt`
- No Docker / CI / IaC in this assignment
