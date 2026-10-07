# Medic

Local coursework app for a small private diagnostic clinic: capacity recovery, payment reconciliation, and a simple equipment investment comparison. Working brand may still change; override with `APP_NAME` if needed.

## Current status (2026-10-07)

Professor use-case approval: **confirmed by student**.

Runnable foundation is in place:

- Flask app starts with `python app.py`
- SQLite file at `DATA_DIR/clinic.sqlite3` (default `./data/clinic.sqlite3`)
- Overview + Capacity screens (sessions, requests, bookings, cancel)
- Unit tests for persistence and core conflict/cancel rules
- Payments and investment UI/logic: **not built yet**

## Setup and run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000` (server binds `0.0.0.0`).

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8000` | HTTP port |
| `DATA_DIR` | `./data` | Directory for SQLite |
| `APP_NAME` | `Medic` | Visible product name |
| `SECRET_KEY` | `medic-dev-only` | Flask flash sessions (change if needed) |

Database path: `DATA_DIR/clinic.sqlite3`. Schema is created automatically; fictional seed data is inserted only when the database has no procedure types yet. Restart does not wipe your data.

## Testing

```bash
python -m pytest
```

Core operations coverage check (run after more finance tests exist; threshold is assignment minimum):

```bash
python -m pytest --cov=clinic.operations --cov=clinic.finance --cov-report=term-missing
```

Measured on 2026-10-07 after foundation work: `11 passed` with `python -m pytest`. Full ≥70% coverage claim for both domains waits until finance logic exists.

## Layout (short)

- `app.py` — start command
- `clinic/` — app factory, DB, schema, seed
- `clinic/operations/` — capacity rules + routes
- `clinic/finance/` — package reserved for money domain
- `clinic/application.py` — future ops↔finance orchestration
- `tests/` — persistence + conflict/cancel tests
- `ADR.md`, `AI_USAGE.md`, `PROJECT_BRIEF.md`, `ACCEPTANCE_CRITERIA.md`

## Assignment notes

- Single process, one SQLite file, one root `requirements.txt`
- No Docker / CI / IaC in this assignment
