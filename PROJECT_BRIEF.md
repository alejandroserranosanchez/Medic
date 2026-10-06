# CareQuanta — Project Brief

**Working name:** CareQuanta (provisional; final brand not selected)  
**Date:** 2026-10-06  
**Delivery target:** 2026-10-12 (course deadline corrected by student; confirm submission hour in the portal)  
**Professor approval:** **Pending** — do not treat silence as approval. Application code waits until Alejandro records explicit confirmation.

## User problem

The manager of a small private diagnostic clinic needs one local tool that answers three related questions with transparent rules and persisted records:

1. Can we use available appointment capacity better after cancellations?
2. Have completed procedures been paid correctly against expected fees?
3. Would keeping, buying, or leasing equipment improve the clinic’s economics under stated assumptions?

## Target user / buyer

- **Primary user:** clinic manager / operations coordinator of a small private diagnostic clinic.
- **Buyer context (course framing):** a single clinic deciding whether this local workflow is useful enough to adopt; not a hospital IT procurement exercise.
- **Out of band:** no clinician, hospital access, real patient data, or external API is required to build the assignment version.

## Product boundaries (first release)

| Area | In scope by 12 October | Explicitly later |
|---|---|---|
| Capacity | View sessions/bookings, cancel a booking, explain eligible replacement requests, confirm one without double booking | More specialties, multi-resource scheduling, real clinic imports, patient outreach |
| Payments | Record completed activity with expected fee; record one or more payments; explain unpaid / partial / settled / overpaid | Insurer contracts, remittance import, doctor revenue sharing, disputes, accounting integrations |
| Investment | Save one keep/buy/lease comparison per procedure type with explicit demand, staffing, room, and equipment assumptions | Detailed simulation, mixed procedures, financing, tax, residual value, discounting |

Constraints for this release: one product, one clinic, one currency (EUR), one time zone, two procedure types (gastroscopy and colonoscopy). All data is fictional.

## Two backend domains

### Domain A — Clinic operations

Owns procedure definitions, staffed sessions, waiting requests, bookings, and recovery proposals. Responsibilities: valid booking intervals, cancellation/completion transitions, conflict detection, candidate eligibility, and deterministic prioritisation.

### Domain B — Clinic finance

Owns procedure fee assumptions, receivables, payments, and saved investment scenarios. Responsibilities: expected-versus-paid balances, immutable historical fee snapshots, duplicate payment prevention, financial calculations, and scenario persistence.

### Boundary (design intent; not implemented while approval is pending)

Operations must not import finance. Finance must not read operations tables directly. A small application service will coordinate booking completion and receivable creation. Both domains share one SQLite database in this monolith.

## Exclusions

- No Dockerfile, Compose, CI workflows, or IaC authored for this assignment.
- No public deployment, external managed DB/cache/queue, Redis, Celery, or microservices.
- No real patient data, diagnosis, payment processing, or hospital/insurer integrations.
- No claim that simplified session rules prove clinical feasibility.
- No full application implementation until professor approval is recorded.

## Acceptance targets (summary)

Detailed cases live in `ACCEPTANCE_CRITERIA.md` (checkpoint 2 while approval is pending). High-level targets:

- Capacity: half-open occupied intervals including turnover; replacement eligibility with ranked candidates and stale-proposal rejection; one receivable per completed booking.
- Payments: fee snapshot at completion; multiple payments allowed; duplicate payment references ignored; status labels for unpaid/partial/settled/overpaid; overdue separate from balance labels.
- Investment: keep/buy/lease arithmetic with bottleneck explanation; save/reload preserves assumptions and outputs; reject invalid inputs.

## Tech direction (adopted for ADR-1)

Python + Flask + Jinja + local CSS/minimal JS + stdlib `sqlite3`, with `pytest` / `pytest-cov` for tests. Stack chosen so the student can explain the code cold. Dependency set starts small; versions recorded only when actually installed.

## Startup contract (planned; not running yet)

```bash
python -m pip install -r requirements.txt
python app.py
```

- Bind `0.0.0.0`; `PORT` default `8000`; `DATA_DIR` default `./data`; DB path `DATA_DIR/clinic.sqlite3`.
- No required `.env`; noninteractive schema init; Flask debug reloader off so one process matches the documented start command.

## Approval status

| Item | Status |
|---|---|
| Use-case proposal drafted for professor | Yes (see plan section 11 text; send personally) |
| Professor preapproval recorded by Alejandro | **Pending** |
| Application / schema / tests started | **No** — documentation-only path while pending |

---

## Day-by-day backlog (planned real work; not pre-generated commits)

Dates use Europe/Madrid. Adjust if needed; never fabricate completed work.

| Date | Checkpoint focus |
|---|---|
| Tue 6 Oct | Product brief + process docs; acceptance specification (tonight — docs only while approval pending) |
| Wed 7 Oct | Confirm approval; Flask foundation, schema, persisted operations forms; booking conflict/cancellation + tests |
| Thu 8 Oct | Replacement candidates and saved proposals; transactional accept/complete + receivable + edge tests |
| Fri 9 Oct | Payments persistence and reconciliation statuses; payment screen + duplicate/partial/overpaid tests |
| Sat 10 Oct | Keep/buy/lease calculations and saved assumptions; scenario UI + bottleneck/financial tests |
| Sun 11 Oct | Demo flow, measured coverage, startup checks; README, diagrams, 4–5 page report, comprehension review |
| Mon 12 Oct | Submission buffer and genuine final corrections only |

Target cadence: two substantive commits per development day, pushed the same day, keeping any single day under 40% of total commits.

---

## Data and architecture proposal (not decided/implemented yet)

The following separates **proposal** from **decided**. Do not create these tables in code while approval is pending.

### Decided already

- Backend: Python + Flask + Jinja + stdlib `sqlite3` (ADR-1).
- One SQLite file for both domains; planned path `DATA_DIR/clinic.sqlite3`.
- Documentation-only progress until professor approval is recorded by Alejandro.

### Proposed module shape (introduce only as needed after approval)

- `app.py` — environment-driven launch
- `clinic/` — factory, `db.py`, `schema.sql`, `application.py`, `seed.py`
- `clinic/operations/` — routes, service, repository
- `clinic/finance/` — routes, reconciliation, investment, repository
- `clinic/templates/` + `clinic/static/`
- `tests/` — operations, reconciliation, investment, persistence/startup
- Root: `requirements.txt`, `README.md`, `ADR.md`, `AI_USAGE.md`, this brief, `ACCEPTANCE_CRITERIA.md`

### Proposed tables (refine at schema milestone; future ADR-3)

| Table | Ownership | Main idea |
|---|---|---|
| `procedure_types` | Operations | Unique code, duration/turnover |
| `sessions` | Operations | Room, clinician, date, start/end; reject shared-resource overlap |
| `requests` | Operations | Fictional reference, priority, readiness, availability, minimum notice |
| `bookings` | Operations | Request + session, interval, status; one active booking per request |
| `recovery_proposals` | Operations | Cancelled booking, candidate, slot, reasons, status; no effect until accepted |
| `fee_assumptions` | Finance | Procedure expected fee and variable cost (current assumptions) |
| `receivables` | Finance | Unique `source_booking_id`, fee snapshot, dates |
| `payments` | Finance | Receivable FK, unique payment reference, positive cents, paid date |
| `investment_scenarios` | Finance | Name, model version, input/output snapshots |

Proposed money rule: integer euro cents; `Decimal` for user input. Enable SQLite foreign keys for internal relationships. Prefer parameterised SQL and explicit transactions. Restrict deletion of completed activity or receivables with payments.

Boundary proposal: `source_booking_id` as a stable reference across domains (or a deliberate FK if chosen later). Document the trade-off in ADR-3 when the schema is selected.
