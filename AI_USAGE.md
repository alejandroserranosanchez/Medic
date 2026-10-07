# AI usage log

Disclosure is grade-neutral. The last column must be completed or verified by Alejandro in his own words. Cursor must not invent student explanations.

| Date/commit | Tool | Prompt | Disposition (Accepted/Modified/Rejected) | What changed & why (if modified) | In my own words, how this works |
|---|---|---|---|---|---|
| 2026-10-06 / `d812655` | Cursor | Checkpoint 1 docs while approval pending. | Accepted | Created `PROJECT_BRIEF.md`, planning `README.md`, ADR-1, this log structure. | **TODO (Alejandro)** |
| 2026-10-06 / `2f29bd9` | Cursor | Checkpoint 2A acceptance criteria + backlog while approval pending. | Accepted | Added `ACCEPTANCE_CRITERIA.md`, backlog/proposal in brief, `.gitignore`. | **TODO (Alejandro)** |
| 2026-10-07 / *(pending local commit 1)* | Cursor | After approval: build Flask/SQLite foundation; student commits/pushes without Cursor co-author. | Accepted (implementation; not yet committed when this row was written) | Added `app.py`, `clinic/` factory/db/schema/seed, Overview + Capacity UI, `requirements.txt` (Flask 3.1.3, pytest 9.0.2, pytest-cov 7.1.0), persistence restart test. | **TODO (Alejandro):** Explain `create_app`, `DATA_DIR`/`clinic.sqlite3`, and why seed runs only once. |
| 2026-10-07 / *(pending local commit 2)* | Cursor | Same day: conflict/cancel rules, tests, ADR-2/3. | Accepted (implementation; not yet committed when this row was written) | Added operations service/repository rules, conflict/turnover/cancel tests (11 passed locally), ADR-2 domain boundary, ADR-3 schema/`source_booking_id`. | **TODO (Alejandro):** Explain half-open intervals + turnover, and why cancel does not create a receivable. |
| 2026-10-07 / *(pending guide commit, usually with commit 2)* | Cursor | Read full `CURSOR_REVIEW_AND_BUILD_GUIDE.md` (updated with §6.5 clinician/procedure profiles); inspect Git; reconcile 7 Oct milestones; do not reimplement or start profiles today (planned 8 Oct). | Accepted (documentation / planning only) | Copied guide to repo root as reference. Confirmed foundation+capacity code existed locally but was **not** on `origin/main`. No profile/F1–F4 implementation in this interaction. Recorded honest Git reconciliation. | **TODO (Alejandro):** Note what the guide changed for tomorrow (profiles, snapshots, `BEGIN IMMEDIATE`) in your own words. |

Notes for Alejandro:

- Fill every **TODO** cell before the pre-submission explanation day.
- After you commit, replace `*(pending …)*` with the real short hashes.
- Prefer naming real functions (`session_conflicts`, `cancel_booking`, `occupied_end_minutes`) in your explanations.
