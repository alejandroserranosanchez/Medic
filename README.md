# CareQuanta

Provisional working name for an Individual Assignment 1 coursework project: a **local** clinic operations and finance application for a small private diagnostic clinic.

## Current status (2026-10-06)

This repository is in the **planning / documentation** stage.

- Professor use-case approval: **pending** (not recorded yet).
- The application is **not** implemented and **does not** run yet.
- There is no installable dependency lock for an app runtime until foundation work begins after approval.
- Do not expect `python app.py` to work today.

What exists so far:

- `PROJECT_BRIEF.md` — problem, users, domains, exclusions, approval status
- `ADR.md` — Architecture Decision Records (ADR-1 only so far)
- `AI_USAGE.md` — AI interaction log (student own-words column must be completed by Alejandro)

## Planned product (after approval)

Three product areas on one Flask process and one SQLite database:

1. **Capacity** — sessions, bookings, cancellation, explainable replacement proposals
2. **Payments** — expected fees, payments, reconciliation status labels
3. **Investment** — keep / buy / lease scenario comparison with saved assumptions

Two backend domains: **clinic operations** and **clinic finance**, coupled only through an explicit application service at the completion/receivable boundary.

## Planned run contract (not active yet)

Once the foundation exists, the intended local start path will be:

```bash
python -m pip install -r requirements.txt
python app.py
```

Environment defaults (planned): `PORT=8000`, `DATA_DIR=./data`, database file `DATA_DIR/clinic.sqlite3`.

## Testing

No test suite yet. Coverage commands and measured results will be recorded here only after tests exist and are run.

## Assignment notes

- Single process, single SQLite file, one root dependency manifest.
- No Docker/CI/IaC authored in this assignment.
- Commit history and process docs (`ADR.md`, `AI_USAGE.md`) are part of the graded evidence.
