# AI usage log

Disclosure is grade-neutral. The last column must be completed or verified by Alejandro in his own words. Cursor must not invent student explanations.

| Date/commit | Tool | Prompt | Disposition (Accepted/Modified/Rejected) | What changed & why (if modified) | In my own words, how this works |
|---|---|---|---|---|---|
| 2026-10-06 / `d812655` | Cursor | Checkpoint 1 docs while approval pending. | Accepted | Planning brief, README, ADR-1, log structure. | **TODO (Alejandro)** |
| 2026-10-06 / `2f29bd9` | Cursor | Checkpoint 2A acceptance criteria. | Accepted | `ACCEPTANCE_CRITERIA.md`, backlog, `.gitignore`. | **TODO (Alejandro)** |
| 2026-10-07 / `d035854` | Cursor | Flask/SQLite foundation after approval. | Accepted | App factory, schema/seed, Overview/Capacity shell, persistence test. | **TODO (Alejandro)** |
| 2026-10-07 / `329d1a2` | Cursor | Capacity conflicts + ADR-2/3. | Accepted | Conflict/cancel rules and tests; domain/schema ADRs. | **TODO (Alejandro)** |
| 2026-10-07 / (with capacity docs) | Cursor | Read review guide; reconcile Git; no profiles yet. | Accepted | Added `CURSOR_REVIEW_AND_BUILD_GUIDE.md` as reference. | **TODO (Alejandro)** |
| 2026-10-09 / *(pending)* | Cursor | Friday 9: catch up Oct-8 P0 (profiles, derived duration, eligibility, IMMEDIATE txs) then Finance complete+payments; keep explainable. | Accepted | Profiles §6.5, booking snapshots, eligibility, validation, `BEGIN IMMEDIATE`; `complete_booking` + receivables/payments + ADR-4. 26 tests passed locally. | **TODO (Alejandro):** Explain `compute_timing_plan` and why `complete_booking` lives in `application.py`. |

Notes for Alejandro:

- Fill every **TODO** before the pre-submission explanation day.
- After you commit, paste real short hashes into the Date/commit column.
- Defence phrases to practise: half-open intervals; profile vs catalogue; snapshot immutability; `BEGIN IMMEDIATE`; Operations vs Finance vs application service.
