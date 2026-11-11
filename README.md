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

Database path: `DATA_DIR/clinic.sqlite3`. Seed data is inserted only when `procedure_types` is empty, so a later start does not insert the demo rows again and does not delete bookings added from the forms.

## Run in the provided container

`Dockerfile` is the Assignment 1 template with its four marked lines filled: `python:3.12-slim`, install `requirements.txt`, copy `app.py` and `clinic/`, and start `python app.py`. The template sets `DATA_DIR=/data`. Docker Desktop must be running.

```bash
docker build -t medic .
docker run --rm -p 8000:8000 -v medic-data:/data medic
```

Open `http://localhost:8000`. Inside the container the database file is `/data/clinic.sqlite3`, on the volume `medic-data`. On the laptop, with `DATA_DIR` unset, the file is `data/clinic.sqlite3` in the project. Those are different folders.

A local start on 22 October 2026 built the image, answered HTTP 200, and created `/data/clinic.sqlite3`. The graded checker is still to be pasted here:

```bash
./container/run.sh /path/to/Medic
```

Run that from a clone of the professor's `sdd-assignment-1` repository. The passing output belongs under this heading.

## Local SQL Server for Assignment 2

This Compose file starts SQL Server, creates the `operations` and `finance` databases, and starts a small service for each. Those services only answer `GET /health`. They do not schedule bookings or record payments. The original clinic still uses SQLite:

```bash
python app.py
```

On an Apple Silicon Mac, enable Rosetta emulation in Docker Desktop. The image is `linux/amd64`.

```bash
cp .env.example .env
```

Edit `.env` and replace the three passwords. Then:

```bash
docker compose up --build
```

The first start downloads SQL Server, which can take several minutes. `db/init.sql` creates the databases and one login each. A named volume, `medic-sql-data`, keeps those files. The next `docker compose up` reuses them. The script can run again without deleting rows.

`docker compose down` stops the containers and keeps the volume. `docker compose down -v` deletes the volume and the databases with it.

The administrator password is only for this local server and the init script. `operations_user` can use `operations`. `finance_user` can use `finance`. Neither login is a user in the other database.

Operations is published on port 8001 and Finance on port 8002. Inside Compose they call SQL Server by the name `sqlserver`, not `localhost`.

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8002/health
```

Service checks, from each service folder:

```bash
pip install -r requirements.txt -r requirements-dev.txt
ruff check .
pytest
```

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
- The Dockerfile is the provided template with its four marked lines filled. No Compose file, CI workflow, or infrastructure-as-code is part of this submission.
