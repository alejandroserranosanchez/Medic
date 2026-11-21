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
Status: Superseded by 6
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

Note (2026-10-09): Schema grew with `clinicians`, `clinician_procedure_profiles`, and booking timing snapshots (`planning_block_minutes`, `room_turnover_minutes`, …). Catalogue FK from `fee_assumptions.procedure_code` remains a known monolith dependency (not full storage independence). Idempotent migration lives in `clinic/db.py`.

## [4]. Testing focuses on business rules, not Flask routes

Date: 2026-10-09
Status: Decided
Context: The assignment requires ≥70% coverage on core business logic for both domains. Route tests alone would inflate coverage without proving scheduling or money rules.
Decision: Prefer pytest on pure functions (`compute_timing_plan`, `eligibility_issues`, `classify_balance`) and repository/application flows with temporary SQLite. Measure `clinic.operations`, `clinic.finance`, `clinic.application`, and `clinic.timeutil`. Keep HTTP checks thin.
Alternatives considered: Maximising coverage via route-only tests was rejected because it hides defects like ignored duration and missing eligibility. A separate end-to-end browser suite was rejected as too heavy for this deadline.
Consequences: We must keep decision logic out of templates. Finance and Operations each need enough rule tests that one domain cannot hide the other’s thin coverage.

## [5]. Deliberate omission of live hospital/insurer integrations

Date: 2026-10-10
Status: Decided
Context: Real clinics use hospital scheduling, insurer remittance files, and capital-planning tools. Connecting to them would add credentials, privacy risk, and deployment surface the assignment forbids for this phase.
Decision: Keep Medic fully local with fictional data, deterministic rules, and saved investment scenarios that explain bottlenecks. Do not integrate EndoSoft-like schedulers, insurer remittances, payment processors, or public cloud APIs in Assignment 1.
Alternatives considered: A read-only CSV import of “real-looking” clinic exports was rejected for this week because it adds validation/privacy work without helping the graded domains. Building a fake external HTTP stub was rejected as theatre that complicates the comprehension check.
Consequences: The demo must show transparent local calculations instead of vendor integrations. After the course, discovery interviews and authorised imports are the next product step — not part of this repository’s scope.

## [6]. Operations calls Finance when a booking is completed

Date: 2026-11-21
Status: Decided
Context: Assignment 2 splits the two domains into separate processes and separate databases. ADR-2 put the completion workflow in one SQLite transaction. That transaction cannot cross SQL Server databases. The clinic still needs one completed booking to produce one receivable. The established fees remain GASTRO 12000 cents and COLONO 18000 cents, from the Assignment 1 catalogue.
Decision: Operations owns the booking status. Finance owns receivables, payments, and the fee catalogue. Operations calls `POST /receivables` at `FINANCE_SERVICE_URL`. It sends the booking id, procedure code, and dates. It does not send a fee. Finance looks up the catalogue and stores the snapshot. `source_booking_id` stays a unique label, not a foreign key. Neither service reads the other database. The hostname is configuration, in Compose `http://finance:8000`, and on Azure the Finance app's HTTPS address.
Alternatives considered: Keeping one SQL transaction was rejected because the databases are now separate. Letting the browser call both services was rejected for this flow because the assignment requires one server-side call across the seam. Copying the fee numbers into Operations was rejected because the fee belongs to Finance and would drift. A queue was rejected because the assignment forbids a broker.
Consequences: The domain split from ADR-2 remains. The single-database transaction does not. A Finance outage does not change Operations `GET /health`, because health only touches the Operations database. Completion can be left unfinished, which ADR-7 describes. ADR-8, ADR-9, and ADR-10 are not written yet.

## [7]. A lost Finance reply is not a successful completion

Date: 2026-11-21
Status: Decided
Context: There is no distributed transaction. Finance can save the receivable and then lose the network reply. A retry must not create a second receivable, and Operations must not tell the caller the booking is completed while the money result is unknown.
Decision: The booking becomes `completion_pending` before the HTTP call. The call has a finite timeout, 3 seconds unless `FINANCE_TIMEOUT_SECONDS` sets a value greater than 0 and at most 30. Any other setting falls back to 3 seconds. Connection refused on the first attempt means Finance did not receive it, so the booking returns to `active` and the response is 503. A timeout, a connection drop, or an HTTP 5xx leaves `completion_pending` and returns 503. The response is not success. A later attempt sends the same details. Finance returns the existing receivable with HTTP 200 when the procedure, dates, and fee match, and HTTP 409 when they do not. Operations stores `finance_receivable_id` only after HTTP 200 or 201, then marks the booking `completed`. A repeated completion of that booking returns the stored id and does not call Finance. A booking that has not started is rejected locally and Finance is not called.
Alternatives considered: Marking the booking completed before the call was rejected because a timeout would report success with no known receivable. Retrying forever was rejected. Adding a background worker was rejected because it is a second system and the assignment does not ask for one. Treating every Finance 409 as "already done" was rejected because a conflicting fee or date must not be accepted.
Consequences: The patient can be asked to complete again after a timeout. Until that retry, the booking is visibly pending. The fee snapshot is frozen on the first successful Finance save. If the catalogue later changes, a retry with the new fee conflicts instead of rewriting the charge. `003_completion_state.sql` adds the pending status and the nullable Finance id to bookings that already exist. `003_fee_assumptions.sql` adds the catalogue. Neither file rewrites an earlier migration.

