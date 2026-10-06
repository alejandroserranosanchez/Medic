# AI usage log

Disclosure is grade-neutral. The last column must be completed or verified by Alejandro in his own words. Cursor must not invent student explanations.

| Date/commit | Tool | Prompt | Disposition (Accepted/Modified/Rejected) | What changed & why (if modified) | In my own words, how this works |
|---|---|---|---|---|---|
| 2026-10-06 / `460d411` (`docs: define clinic operations and finance MVP with bounded scope`) | Cursor (Composer) | Read `CURSOR_PROJECT_PLAN.md` and assignment constraints; use CareQuanta as provisional name; inspect folder/Git; complete tonight’s section 8 checkpoint 1 only (docs path while professor approval pending); one meaningful commit and push after the checkpoint; do not build the app or fabricate approval/dates/own-word explanations. | Accepted (documentation scope) | Created planning docs only: `PROJECT_BRIEF.md`, `README.md` (honest non-running state), `ADR.md` with ADR-1 only, and this `AI_USAGE.md` structure. No application code. | **TODO (Alejandro):** Replace this cell with your own short explanation of what these planning files are for and how ADR-1’s Flask choice connects to the assignment’s single-process / explain-cold requirements. Do not leave the TODO in the submitted final log. |
| 2026-10-06 / *(second commit hash after push attempt)* | Cursor (Composer) | Continue section 8 checkpoint 2A while approval pending: acceptance cases, backlog + data/architecture proposal in the brief, `.gitignore`, update this log; second meaningful commit and push; no executable app code. | Accepted (documentation scope) | Added `ACCEPTANCE_CRITERIA.md` from plan section 5 cases; extended `PROJECT_BRIEF.md` with day-by-day backlog and proposed (not implemented) schema/modules; added Python/Flask `.gitignore`; updated README inventory. Still no application code, schema SQL, or tests. | **TODO (Alejandro):** In your own words, explain how one capacity case and one payment case will later become tests (name the inputs/expected outcomes you care about). |

Notes for Alejandro:

- After the second commit exists, replace the placeholder in the second row’s Date/commit cell with the real short hash.
- Never paste vague text into the last column; name real files, functions, and decisions from this repo once code exists.
