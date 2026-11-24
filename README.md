# Medic (Assignment 2)

Medic is a coursework app for a small private diagnostic clinic. All data is fictional.

**Assignment 2** is the current system: two Flask HTTP services (Operations and Finance), each with its own SQL Server database, a static browser UI, Docker Compose locally, and Azure Container Apps plus Azure Storage for the live site.

**Live UI:** https://aserranoieu2024ui.z28.web.core.windows.net/

**Live APIs (public HTTPS):**

- Operations: https://aserrano-ieu2024-operations.proudpebble-d865b3c1.francecentral.azurecontainerapps.io  
- Finance: https://aserrano-ieu2024-finance.proudpebble-d865b3c1.francecentral.azurecontainerapps.io  

**Repository:** https://github.com/alejandroserranosanchez/Medic

The Assignment 1 monolith (one process, SQLite, Jinja screens) remains for history. See [Legacy: Assignment 1](#legacy-assignment-1). Do not treat that section as the live architecture.

| Document | Role |
|---|---|
| [`docs/report-assignment-2.md`](docs/report-assignment-2.md) | Assignment 2 report (4–5 pages) |
| [`docs/report.md`](docs/report.md) | Assignment 1 report (unchanged) |
| [`ADR.md`](ADR.md) | Architecture decisions 1–10 |
| [`AI_USAGE.md`](AI_USAGE.md) | AI disclosure log |
| [`system.yaml`](system.yaml) + [`system.schema.json`](system.schema.json) | Machine-readable system contract |
| `services/*/openapi.yaml` | Per-service HTTP contracts |
| [`docs/evidence/`](docs/evidence/) | Local test / Compose transcripts (no secrets) |

## What works today

- Create sessions and bookings (**Operations**)
- Complete a started booking; Operations calls Finance over HTTP for one receivable (server-side seam)
- Look up a receivable and record a payment (**Finance**)
- Fees in Finance: **GASTRO 12000** / **COLONO 18000** cents (EUR; see migration `004`)

Not in the Assignment 2 APIs/UI (still only in the Assignment 1 monolith): keep/buy/lease equipment comparison, slot-recovery ranking, Jinja Overview/Schedule/Collections screens.

## Architecture

```mermaid
flowchart LR
  Browser["Browser<br/>ui/ static files"]
  UI["Azure Storage static website<br/>aserranoieu2024ui<br/>or nginx:8080 locally"]
  Ops["Operations<br/>Flask · Container App"]
  Fin["Finance<br/>Flask · Container App"]
  OpsDB[("operations DB")]
  FinDB[("finance DB")]

  Browser --> UI
  Browser -->|"HTTPS JSON + CORS"| Ops
  Browser -->|"HTTPS JSON + CORS"| Fin
  Ops -->|"POST /receivables<br/>urllib.request"| Fin
  Ops --> OpsDB
  Fin --> FinDB
```

Flask routes expose JSON; business rules live in modules such as `completion.py` / `receivables.py`; Operations reaches Finance with `urllib.request` and a timeout; each service uses `pymssql` against its own `DATABASE_URL`. CORS allows only `UI_ORIGIN`.

## Run the full stack (Docker Compose)

Requires Docker Desktop. On Apple Silicon, enable Rosetta; the SQL Server image is `linux/amd64`.

```bash
cp .env.example .env
# Edit .env: set MSSQL_SA_PASSWORD, OPERATIONS_DB_PASSWORD, FINANCE_DB_PASSWORD
# (letters/digits only; see comments in .env.example — never commit .env)
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:8080 | Static UI (`nginx:alpine`; not a third domain service) |
| http://127.0.0.1:8001 | Operations |
| http://127.0.0.1:8002 | Finance |

Open the UI as **localhost**, not `127.0.0.1` (CORS uses `UI_ORIGIN=http://localhost:8080`).

`db/init.sql` (one-off `sql-init`) creates the `operations` and `finance` databases and one login each. Volume `medic-sql-data` keeps data across `docker compose down`. `docker compose down -v` deletes the volume.

```bash
curl -sS http://127.0.0.1:8001/health
curl -sS http://127.0.0.1:8002/health
```

Healthy shape: `{"status":"ok","db":"ok","version":"<git sha>"}`. Local images without `GIT_SHA` return `"unknown"`.

## Run one service independently

1. Start only SQL + init (and the peer if you need the seam):

```bash
docker compose up -d sqlserver
docker compose up sql-init    # exits 0 when databases/logins exist
# Optional peer for completion:
docker compose up -d finance
```

2. From the service folder, with passwords from `.env` (example for Operations):

```bash
cd services/operations
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export DATABASE_URL="mssql://operations_user:${OPERATIONS_DB_PASSWORD}@127.0.0.1:1433/operations"
export FINANCE_SERVICE_URL="http://127.0.0.1:8002"
export FINANCE_TIMEOUT_SECONDS=3
export UI_ORIGIN="http://localhost:8080"
export TZ=Europe/Madrid
export PORT=8001
python -m app.main
```

Finance is the same pattern with `services/finance`, `finance_user` / `finance` database, `PORT=8002`, and no `FINANCE_SERVICE_URL`.

## Tests and coverage

Needs local SQL Server reachable on `127.0.0.1:1433` (Compose `sqlserver`) and passwords in `.env`. CI uses its own SQL Server service container and **never** opens Azure SQL.

```bash
# Operations
cd services/operations
pip install -r requirements.txt -r requirements-dev.txt
ruff check .
pytest --cov=app --cov-report=term-missing --cov-fail-under=70 -v

# Finance
cd services/finance
pip install -r requirements.txt -r requirements-dev.txt
ruff check .
pytest --cov=app --cov-report=term-missing --cov-fail-under=70 -v
```

## Environment variables and secrets

Full list: [`system.yaml`](system.yaml).

| Variable | Who | Notes |
|---|---|---|
| `DATABASE_URL` | Both | **Secret.** That service’s database only. |
| `PORT` | Both | Default `8000` in the container. |
| `GIT_SHA` | Both | Build-arg; returned by `/health`. Default `unknown`. |
| `UI_ORIGIN` | Both | CORS origin. Empty = none. Compose: `http://localhost:8080`. Azure: Storage origin **without** trailing slash. |
| `FINANCE_SERVICE_URL` | Operations | App default `""` (unconfigured). Compose: `http://finance:8000`. Azure: Finance HTTPS FQDN. |
| `FINANCE_TIMEOUT_SECONDS` | Operations | Default `3`. |
| `TZ` | Both | Compose/Azure: `Europe/Madrid`. |

GitHub Actions secrets (OIDC): `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, plus `OPERATIONS_DATABASE_URL` / `FINANCE_DATABASE_URL`. Never put secrets in `ui/config.js`, source, Compose, or images.

## Migrations

Numbered `.sql` under `services/<name>/migrations/`. On startup, `apply_migrations()` runs pending files, records them in `schema_migrations`, and prints `Applied migration: <file>` **after** a successful commit. Applied files are not edited.

| Service | Files |
|---|---|
| Operations | `001_sessions.sql`, `002_bookings.sql`, `003_completion_state.sql` |
| Finance | `001_receivables.sql`, `002_payments.sql`, `003_fee_assumptions.sql`, **`004_receivable_currency.sql`** |

`003_completion_state.sql` and `004_receivable_currency.sql` alter **existing** tables without dropping them (ADR-7). Finance `004` is live on Azure SQL `aserrano-ieu2024-finance-db`: receivable **1** kept id/booking/fee/dates and gained `currency_code = EUR` after deploy of `193346c…` (see ADR-7). Recovery for a bad migration is manual (inspect / restore / forward fix).

## Cross-seam completion (partial failure)

1. Operations sets `completion_pending`, then calls Finance `POST /receivables` with timeout.
2. Finance looks up the fee; Operations does not send the amount.
3. HTTP 200/201 → store `finance_receivable_id`, mark `completed`.
4. **Confirmed connection refused** (first attempt) → back to `active`, HTTP 503.
5. **Timeout / drop / HTTP 5xx** → stay `completion_pending`, HTTP 503.
6. Matching retry → Finance returns the same receivable (no second charge).

Local evidence: [`docs/evidence/operations-failure-tests-verbose.txt`](docs/evidence/operations-failure-tests-verbose.txt), [`docs/evidence/compose-partial-failure-local.txt`](docs/evidence/compose-partial-failure-local.txt).

## CI and automatic CD

On **push to `main`** (PRs stop after test + image **build**, no Azure):

**contracts + test (≥70%) → GHCR images tagged with full commit SHA → Deploy Azure → Deploy UI**

| Workflow | Role |
|---|---|
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | Push/PR: contracts, Ruff, pytest, image build; on `main`, push GHCR tags and call CD |
| [`.github/workflows/deploy-azure.yml`](.github/workflows/deploy-azure.yml) | `workflow_call` only: tip-of-`main` guard → Container Apps → `/health` must match SHA → call UI deploy |
| [`.github/workflows/deploy-ui.yml`](.github/workflows/deploy-ui.yml) | Nested call: check out `ui/` at same SHA, write `config.js`, upload `$web`, verify HTTP 200 |

Concurrency group `medic-production-cd` serialises the whole backend+UI run. No `workflow_dispatch`; retries use **Re-run failed jobs**. Changes reach `main` through pull requests.

Verified automatic CD:

| Run | Commit | Notes |
|---|---|---|
| https://github.com/alejandroserranosanchez/Medic/actions/runs/45465579181 | `193346c24066ec97c9b765893cf1c6964176b516` (PR #19, Finance `004`) | Ops 49 / 91.27%; Finance 35 / 89.74%; health + UI OK; Azure DB shows `004` applied |
| https://github.com/alejandroserranosanchez/Medic/actions/runs/45446852738 | `235058bb…` | Earlier automatic CD wiring verification |
| https://github.com/alejandroserranosanchez/Medic/actions/runs/45246257719 | (UI) | Failed then fixed: Storage Blob Data Contributor |

## Initial Azure setup (once) and later deploys

**Once (documented here; later app changes go through CI/CD):**

1. Resource group `rg-aserrano` (personal Students subscription used for this coursework).
2. Azure SQL logical server `aserrano-ieu2024-sql` with two serverless databases (`aserrano-ieu2024-operations-db`, `aserrano-ieu2024-finance-db`), one login each, firewall allow Azure services.
3. Container Apps environment `aserrano-ieu2024-env`; apps `aserrano-ieu2024-operations` / `aserrano-ieu2024-finance` (Consumption, min 0 / max 1, external HTTPS, `DATABASE_URL` as secret ref).
4. Storage account `aserranoieu2024ui` with **static website** enabled (`index.html`); grant the GitHub OIDC app **Storage Blob Data Contributor** on that account.
5. Store OIDC + database URL secrets in GitHub; optional repo variable `UI_ORIGIN` = `https://aserranoieu2024ui.z28.web.core.windows.net` (no trailing slash).

**After that:** merge to `main` → automatic CI publishes SHA images and deploys backend + UI. Migrations run at container startup when a new image first boots.

## Health check (deployed)

```bash
curl -sS "https://aserrano-ieu2024-operations.proudpebble-d865b3c1.francecentral.azurecontainerapps.io/health"
curl -sS "https://aserrano-ieu2024-finance.proudpebble-d865b3c1.francecentral.azurecontainerapps.io/health"
```

Expect HTTP 200 and `"version"` equal to the deployed image’s commit SHA. Health is own-database only.

## Known limitations

- Personal `rg-aserrano` vs class `rg-sdd-3a` / `rg-sdd-3b` (grading risk vs brief §7).
- UI on Storage static website (SWA create failed with `RequestDisallowedByAzure`); `system.schema.json` models `storage_account`.
- Cold start + SQL resume (40613) can delay the first request.
- No automatic migration rollback (ADR-7).
- Tag `submission` on the graded `main` SHA once the final documentation bundle is merged (Finance `004` already deployed at `193346c…`).

---

## Legacy: Assignment 1

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000`. Optional professor template container: `docker build -t medic .` then `docker run --rm -p 8000:8000 -v medic-data:/data medic`. See [`docs/report.md`](docs/report.md).
