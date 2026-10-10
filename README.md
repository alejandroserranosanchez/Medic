# Medic

Local coursework app for a small private diagnostic clinic: capacity recovery, payment reconciliation, and a simple equipment investment comparison. Working brand may still change; override with `APP_NAME` if needed.

## Current status (2026-10-09)

Professor use-case approval: **confirmed by student**.

Working now:

- Flask app: `python app.py` → Overview, Capacity, Payments
- SQLite at `DATA_DIR/clinic.sqlite3` with clinicians/profiles and booking timing snapshots
- Booking end time calculated on the server from clinician+procedure profile (or catalogue)
- Complete booking → one receivable (fee snapshot); record payments; statuses unpaid/partial/settled/overpaid
- Optional `DEMO_NOW=YYYY-MM-DDTHH:MM:SS` for a reproducible planning clock
- Investment keep/buy/lease comparison with save/reopen: **available**
- Slot-recovery proposals UI: **not built yet** (optional polish if time remains)

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

Measured on 2026-10-10: `31 passed` with `python -m pytest` after adding investment tests. Re-run coverage yourself before submission and paste the real numbers.

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
