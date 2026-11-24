# Architecture Decision Records

Assignment 1 required five records (ADR-1 to ADR-5). Assignment 2 adds five more (ADR-6 to ADR-10). Entries are written when decisions are made. Older entries stay as history; if a later decision replaces one, only the Status line changes to `Superseded by N`.

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
Consequences: The domain split from ADR-2 remains. The single-database transaction does not. A Finance outage does not change Operations `GET /health`, because health only touches the Operations database. Completion can be left unfinished, which ADR-7 describes.

## [7]. A lost Finance reply is not a successful completion

Date: 2026-11-21
Status: Decided
Context: There is no distributed transaction. Finance can save the receivable and then lose the network reply. A retry must not create a second receivable, and Operations must not tell the caller the booking is completed while the money result is unknown.
Decision: The booking becomes `completion_pending` before the HTTP call. The call has a finite timeout, 3 seconds unless `FINANCE_TIMEOUT_SECONDS` sets a value greater than 0 and at most 30. Any other setting falls back to 3 seconds. Connection refused on the first attempt means Finance did not receive it, so the booking returns to `active` and the response is 503. A timeout, a connection drop, or an HTTP 5xx leaves `completion_pending` and returns 503. The response is not success. A later attempt sends the same details. Finance returns the existing receivable with HTTP 200 when the procedure, dates, and fee match, and HTTP 409 when they do not. Operations stores `finance_receivable_id` only after HTTP 200 or 201, then marks the booking `completed`. A repeated completion of that booking returns the stored id and does not call Finance. A booking that has not started is rejected locally and Finance is not called.
Alternatives considered: Marking the booking completed before the call was rejected because a timeout would report success with no known receivable. Retrying forever was rejected. Adding a background worker was rejected because it is a second system and the assignment does not ask for one. Treating every Finance 409 as "already done" was rejected because a conflicting fee or date must not be accepted.
Consequences: The patient can be asked to complete again after a timeout. Until that retry, the booking is visibly pending. The fee snapshot is frozen on the first successful Finance save. If the catalogue later changes, a retry with the new fee conflicts instead of rewriting the charge. `003_completion_state.sql` adds the pending status and the nullable Finance id to bookings that already exist. `003_fee_assumptions.sql` adds the catalogue. Neither file rewrites an earlier migration.

Addendum (2026-11-23): Each service also evolves its own Azure SQL schema with numbered `.sql` files applied by `apply_migrations()` at startup. Successful filenames are stored in `schema_migrations` and are skipped on the next boot. Applied files are never edited. Operations `003_completion_state.sql` changes the existing `bookings` table after rows can already be present: it adds nullable `finance_receivable_id` and allows status `completion_pending` without dropping the table. There is no automatic rollback. If a migration fails mid-way, the process may refuse to start; a new migration file does not always repair a half-applied change. Recovery is manual: inspect the database, repair or restore from a backup if needed, and only then deploy a corrected forward migration. This addendum does not change the HTTP partial-failure decision above.

## [8]. Azure Container Apps, serverless SQL and migration recovery

Date: 2026-11-23
Status: Decided
Context: Assignment 2 requires two pay-per-use services and one database each, with scale to zero when idle. The clinic is split into Operations and Finance. A first request after idle may start a cold container and may find Azure SQL paused. Schema changes must preserve existing rows. An attempt to create Azure Static Web App `aserrano-ieu2024-ui` in West Europe failed with `RequestDisallowedByAzure` because the Azure for Students subscription blocks that regional deployment. The Static Web App was not deployed.
Decision: Run Operations and Finance as Azure Container Apps on the Consumption plan, minimum replicas 0 and maximum 1, 0.25 CPU and 0.5 Gi each. Keep one Azure SQL logical server with two serverless databases, one login per database, and auto-pause enabled. Put `DATABASE_URL` in Container Apps secrets. Set `TZ=Europe/Madrid` so booking start checks match local Compose. Serve the static UI from nginx in Compose locally; keep the Deploy UI workflow in the repository, but do not claim a live Static Web App until the subscription allows one. Versioned migrations and failed-migration recovery follow the ADR-7 addendum: the code applies forward SQL once and records it; it does not roll migrations back. A broken startup may need manual database repair or restore before a new image can boot cleanly.
Alternatives considered: Always-on App Service or a dedicated Container Apps profile was rejected because idle cost would continue. One shared Azure SQL database was rejected because each service must own its data. Automatic retry loops around every SQL connection were not added; `db.py` keeps a 5 second login and query timeout, and the deploy workflow retries `/health` so a waking database can succeed on a later attempt. Building the UI as a third container was rejected by the assignment limit of two service containers.
Consequences: The first request after idle can take tens of seconds while the container starts and SQL resumes (Azure error 40613 is common during resume). Migrations run once per cold start on a single replica, so two writers do not apply the same file at once. At about 100x traffic we would raise max replicas, raise CPU and memory, and reconsider SQL auto-pause. Integrity across the seam is not a database foreign key; ADR-6 and ADR-7 describe the HTTP label and retry rules. Personal resource group `rg-aserrano` was used when the class group was not available; that remains a grading risk against the brief's shared class resource group.

Addendum (2026-11-23, Storage UI live): After the Static Web App failure above, the public UI was hosted on the existing Storage account `aserranoieu2024ui` with static website hosting enabled. The public URL is `https://aserranoieu2024ui.z28.web.core.windows.net/`. The professor-provided `system.schema.json` models `ui.storage_account` rather than a Static Web App name, and `system.yaml` matches that. The Deploy UI workflow (`workflow_dispatch` from main) signs in with the same GitHub OIDC app registration, confirms the account and static website, writes `ui/config.js` from the live Operations and Finance HTTPS FQDNs, sets both Container Apps’ `UI_ORIGIN` to the website origin without a trailing slash, and uploads `ui/` to the `$web` container with `az storage blob upload-batch --auth-mode login`. It does not use account keys. The GitHub service principal needs Storage Blob Data Contributor on that account; without it the workflow fails with the role-assignment command. Compose still serves the same `ui/` folder with `nginx:alpine`. This addendum does not change the Container Apps or SQL decisions above. Hosting on Storage instead of Static Web Apps remains a deliberate deviation from the brief’s wording, justified by the blocked SWA create and aligned with the schema file in the repository.

## [9]. GitHub Actions CI, image publish and manual Azure deploy

Date: 2026-11-23
Status: Decided
Context: Every push must be tested. Images must be reproducible. Azure must receive a known SHA. The assignment also asks for a clear test story for the cross-service call.
Decision: Use GitHub Actions. On every push and pull request, CI installs each service, runs Ruff, and runs pytest with `--cov-fail-under=70` against a SQL Server service container. CI never opens Azure SQL. After those tests pass, the images job builds both Docker images. On `main` only, it pushes them to GHCR tagged with the full commit SHA. Deploy Azure is a separate `workflow_dispatch` workflow. It signs in with GitHub OIDC, deploys the pinned `IMAGE_SHA` images to the two Container Apps, sets `FINANCE_SERVICE_URL` and `FINANCE_TIMEOUT_SECONDS`, and checks `/health` until both return HTTP 200 with `status=ok`, `db=ok` and `version` equal to that SHA. Cross-seam tests live in Operations: mocked Finance failures, and one test that starts a real Finance process against a separate local database. Request logs write method, path, status and duration to stdout. CI does not validate `system.yaml` because the professor schema file is not in the repository.
Alternatives considered: Deploying automatically on every main push was rejected for this repository because the deploy workflow is intentional and pins an image SHA by hand. Running tests against Azure SQL was rejected because each connection wakes a billed database. A browser-only end-to-end suite was rejected as too heavy for the deadline; Compose and API tests cover the seam instead.
Consequences: A green CI run on main publishes images but does not change Azure by itself. Someone must update `IMAGE_SHA` and run Deploy Azure. A failed test blocks the image push for that commit. What is not tested here includes Azure SQL resume timing in CI, a full browser click path, and OpenAPI or `system.yaml` schema validation in the pipeline.

Addendum (2026-11-23, contracts and deploy wiring): Two later changes update this decision without replacing it. (1) After `system.schema.json` was added at the repository root, CI gained a `contracts` job that validates `system.yaml` with Draft 2020-12 and both OpenAPI files with `openapi-spec-validator`, and checks that Operations’ documented `POST /receivables` call exists in Finance’s OpenAPI. The `images` job now needs both `test` and `contracts`. The earlier sentence “CI does not validate system.yaml” is obsolete. (2) Deploy Azure sets `IMAGE_SHA` to `${{ github.sha }}` of the workflow run (the commit on main when the dispatch runs); there is no separate hand-edited SHA file. Deploy UI is a second manual workflow for the Storage static site (ADR-8 addendum). What remains deliberately not automatic: every merge to main still does not deploy to Azure by itself — someone must run Deploy Azure and, when the UI or origins change, Deploy UI. That is still a gap against the brief’s “no manual steps” CD wording. What is still not tested in CI: Azure SQL resume timing and a full browser click path.

## [10]. No message broker for booking completion

Date: 2026-11-23
Status: Decided
Context: Completing a booking needs Finance to create one receivable. A queue such as RabbitMQ or Kafka could buffer that work if Finance were down. Assignment 2 forbids message brokers unless we deliberately omit them and explain when they would be worth building.
Decision: Do not add a broker. Keep the ADR-6 and ADR-7 design: Operations calls Finance with HTTP, uses a finite timeout, leaves the booking `completion_pending` when the result is unknown, and relies on Finance's unique `source_booking_id` plus identical-replay HTTP 200 so a retry does not create a second receivable. The caller, person or UI, sends the same completion again.
Alternatives considered: A queue with a worker was rejected because it is a third process, needs its own hosting and monitoring, and the assignment lists brokers as out of scope. Fire-and-forget without `completion_pending` was rejected because the clinic would report success while Finance might have failed.
Consequences: The design is smaller and easier to explain, but a pending completion stays visible until someone retries. This is not guaranteed asynchronous delivery. A broker would become worth building if many completions arrived while Finance was paused for long periods, or if several downstream systems had to receive the same event.

