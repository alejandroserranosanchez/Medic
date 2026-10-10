# AI usage log

Disclosure is grade-neutral. The last column must be completed or verified by Alejandro in his own words. Cursor must not invent student explanations.

| Date/commit | Tool | Prompt | Disposition (Accepted/Modified/Rejected) | What changed & why (if modified) | In my own words, how this works |
|---|---|---|---|---|---|
| 2026-10-06 / `d812655` | Cursor | Checkpoint 1 docs while approval pending. | Accepted | Planning brief, README, ADR-1, log structure. | **TODO (Alejandro)** |
| 2026-10-06 / `2f29bd9` | Cursor | Checkpoint 2A acceptance criteria. | Accepted | `ACCEPTANCE_CRITERIA.md`, backlog, `.gitignore`. | **TODO (Alejandro)** |
| 2026-10-07 / `d035854` | Cursor | Flask/SQLite foundation after approval. | Accepted | App factory, schema/seed, Overview/Capacity shell, persistence test. | **TODO (Alejandro)** |
| 2026-10-07 / `329d1a2` | Cursor | Capacity conflicts + ADR-2/3. | Accepted | Conflict/cancel rules and tests; domain/schema ADRs. | **TODO (Alejandro)** |
| 2026-10-07 | Cursor | Read review guide; reconcile Git. | Accepted | Added `CURSOR_REVIEW_AND_BUILD_GUIDE.md` as reference. | **TODO (Alejandro)** |
| 2026-10-09 / `9f80cc1` | Cursor | Catch up P0: profiles, derived duration, eligibility, IMMEDIATE. | Accepted | Clinician profiles, booking snapshots, eligibility, validation. | **TODO (Alejandro):** Explain `compute_timing_plan`. |
| 2026-10-09 / `561c5a3` | Cursor | Complete booking + payments. | Accepted | `complete_booking`, receivables, payment statuses, ADR-4. | **TODO (Alejandro):** Explain why completion lives in `application.py`. |
| 2026-10-10 / *(pending)* | Cursor | Saturday: keep/buy/lease calc + save/reopen UI + ADR-5; keep explainable. | Accepted | `clinic/finance/investment.py`, Investment screen, snapshot persistence, guide-example tests (31 passed locally), ADR-5 no live integrations. | **TODO (Alejandro):** Explain `min(demand, staff, room, equipment)` and why buy can look worse than keep in the guide example. |

Notes for Alejandro:

- Fill every **TODO** before the pre-submission explanation day.
- After you commit today’s work, paste the real short hash(es) into the pending row.
- Defence phrases: half-open intervals; profile snapshots; `BEGIN IMMEDIATE`; application-service completion; investment bottlenecks vs “more equipment always wins”.
