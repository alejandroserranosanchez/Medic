# Architecture Decision Records

Exactly five entries are required by the assignment. Entries are added when decisions are made, not all at once. Only ADR-1 is recorded on 2026-10-06.

## [1]. Backend language and framework: Python + Flask

Date: 2026-10-06
Status: Decided
Context: The assignment needs a single-process web app with SQLite, server-rendered UI, and unit tests I can explain cold at the written comprehension check. The stack must stay small enough to fit one container later without deployment tooling in this assignment.
Decision: Use Python 3 with Flask and Jinja templates, local CSS/minimal JavaScript, and the standard-library `sqlite3` module; plan `pytest` and `pytest-cov` for core business-logic tests.
Alternatives considered: FastAPI plus a separate frontend or JSON-only API was rejected because it adds API/client surface without helping the single-process HTML workflow and would be harder to walk through on paper. Django was rejected as heavier than needed for two domains and four screens with no admin/auth requirements yet.
Consequences: Fast to start and easy to keep one process and one dependency manifest, but we must keep domain logic out of route handlers so tests can hit operations and finance rules without relying on Flask routing coverage alone.
