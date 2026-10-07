# Architecture Decision Records

Exactly five entries are required by the assignment. Entries are added when decisions are made, not all at once.

## [1]. Backend language and framework: Python + Flask

Date: 2026-10-06
Status: Decided
Context: The assignment needs a single-process web app with SQLite, server-rendered UI, and unit tests I can explain cold at the written comprehension check. The stack must stay small enough to fit one container later without deployment tooling in this assignment.
Decision: Use Python 3 with Flask and Jinja templates, local CSS/minimal JavaScript, and the standard-library `sqlite3` module; plan `pytest` and `pytest-cov` for core business-logic tests.
Alternatives considered: FastAPI plus a separate frontend or JSON-only API was rejected because it adds API/client surface without helping the single-process HTML workflow and would be harder to walk through on paper. Django was rejected as heavier than needed for two domains and four screens with no admin/auth requirements yet.
Consequences: Fast to start and easy to keep one process and one dependency manifest, but we must keep domain logic out of route handlers so tests can hit operations and finance rules without relying on Flask routing coverage alone.

## [2]. Two domains with an application-service boundary

Date: 2026-10-07
Status: Decided
Context: The assignment requires two independently modularizable backend feature domains that still run as one process today. Capacity workflows and money workflows must not become a tangled ball of imports.
Decision: Split code into `clinic/operations` (sessions, requests, bookings, recovery) and `clinic/finance` (fees, receivables, payments, investment). Operations never imports finance. Finance never reads operations tables. Future completion-of-booking work goes through `clinic/application.py` in one SQLite transaction.
Alternatives considered: Putting all SQL in one repository module was rejected because it hides the seam we must explain later when splitting services. An event bus or queue was rejected because the assignment forbids multi-process infrastructure now.
Consequences: Clear folders and import rules make the future split visible, but we must remember to keep orchestration out of route handlers so the boundary stays honest.

## [3]. SQLite schema with `source_booking_id` at the domain edge

Date: 2026-10-07
Status: Decided
Context: Both domains must persist in one SQLite file. Completing a booking will create exactly one receivable, but finance should not own a hard dependency on operations table internals forever.
Decision: Use the tables in `clinic/schema.sql`. Money is integer euro cents. Internal operations FKs are normal SQLite foreign keys. Receivables store `source_booking_id` as a unique reference validated by the application service rather than a cross-domain FK, so the finance row remains meaningful if operations were extracted later.
Alternatives considered: A direct `FOREIGN KEY (source_booking_id) REFERENCES bookings(id)` is simpler today but was rejected for ADR clarity: it would couple finance storage to the operations table in a way that fights the planned service split. JSON-only persistence was rejected because relational booking/payment queries are core to the product.
Consequences: The app must enforce the one-receivable-per-completed-booking rule in code/transactions. Diagrams and tests must treat `source_booking_id` as the documented boundary field.
