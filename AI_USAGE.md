# AI usage log

Before the first commit I used **ChatGPT** to draft the project plan (scope, three areas, two domains, day-by-day plan), which I then gave to Cursor as the starting brief. All entries below used **Cursor** (AI coding assistant). For each step I list what I asked, what I did with the output, and my own explanation of how it works. I have used different models such as Claude, Chatgpt and owns Cursor model.

## 2026-10-06 — Project scope (`d812655`)

- **Prompt:** Checkpoint 1 docs while approval pending.
- **Disposition:** Accepted.
- **What changed:** Planning brief, README, ADR-1, log structure.
- **In my own words:** Before writing any code I wrote down what the app is for, who would use it, what is out of scope and why I chose Flask (ADR-1). Approval was still pending, so this day was only the planning phase of the SDLC.

## 2026-10-06 — Acceptance criteria (`2f29bd9`)

- **Prompt:** Checkpoint 2A acceptance criteria.
- **Disposition:** Accepted.
- **What changed:** `ACCEPTANCE_CRITERIA.md`, backlog, `.gitignore`.
- **In my own words:** I turned the business rules into Given/When/Then cases with made-up numbers, so I knew what "done" means before coding. Later most of these cases became pytest tests. `.gitignore` keeps the virtualenv and the database file out of Git.

## 2026-10-07 — Flask and SQLite foundation (`d035854`)

- **Prompt:** Flask/SQLite foundation after approval.
- **Disposition:** Accepted.
- **What changed:** App factory, schema/seed, Overview/Capacity shell, persistence test.
- **In my own words:** `create_app` builds the Flask app and reads `PORT` and `DATA_DIR` from environment variables. On start it creates the SQLite tables if they don't exist and adds demo data only when the database is empty, so restarting never deletes my data. The persistence test restarts the app and checks that a saved session is still there.

## 2026-10-07 — Capacity conflicts, ADR-2 and ADR-3 (`329d1a2`)

- **Prompt:** Capacity conflicts + ADR-2/3.
- **Disposition:** Accepted.
- **What changed:** Conflict/cancel rules and tests; domain/schema ADRs.
- **In my own words:** Two sessions clash if they use the same room or the same clinician and their times overlap. I use half-open intervals `[start, end)`, so 09:00–09:40 and 09:40–10:20 touch but don't overlap. Room turnover (cleaning time) is added after each booking. Cancelling frees the slot. ADR-2 splits the code into Operations and Finance, and ADR-3 explains the tables and why receivables use `source_booking_id` without a foreign key.

## 2026-10-07 — Review guide and Git check

- **Prompt:** Read review guide; reconcile Git.
- **Disposition:** Accepted.
- **What changed:** Added `CURSOR_REVIEW_AND_BUILD_GUIDE.md` as reference.
- **In my own words:** I used a review guide to check what was missing in my plan, and I compared my local Git history with what was already pushed so I didn't redo or duplicate commits.

## 2026-10-09 — Clinician profiles and eligibility (`9f80cc1`)

- **Prompt:** Catch up P0: profiles, derived duration, eligibility, IMMEDIATE.
- **Disposition:** Accepted.
- **What changed:** Clinician profiles, booking snapshots, eligibility, validation.
- **In my own words:** `compute_timing_plan` decides how long a booking takes: `max(centre minimum, clinician estimate + variability)`. For Dr. Vega that is max(30, 25+5) = 30 min and for Dr. Nadal max(30, 35+5) = 40 min. The server calculates the end time, not the user, and the room is busy until end + turnover. The booking saves a copy (snapshot) of these numbers, so changing a profile later doesn't move old bookings. Before booking I also check that the patient is ready, available and has enough notice. `BEGIN IMMEDIATE` locks the database before checking for clashes, so two bookings can't take the same slot at the same time.

## 2026-10-09 — Completing bookings and payments (`561c5a3`)

- **Prompt:** Complete booking + payments.
- **Disposition:** Accepted.
- **What changed:** `complete_booking`, receivables, payment statuses, ADR-4.
- **In my own words:** Completing a booking touches both domains: Operations marks it completed and Finance creates the receivable (what the patient owes). If I put this inside one domain, that domain would depend on the other. So `complete_booking` lives in `application.py` and does both writes in one transaction: if one fails, both are undone. Completing twice returns the same receivable instead of creating a second one. Money is stored in integer cents, and the balance is unpaid, partial, settled or overpaid, with overdue as a separate flag.

## 2026-10-10 — Keep / buy / lease investment (`fb61f5e`)

- **Prompt:** Saturday: keep/buy/lease calc + save/reopen UI; keep explainable.
- **Disposition:** Accepted.
- **What changed:** `clinic/finance/investment.py`, Investment screen, snapshot persistence, guide-example tests (31 passed locally).
- **In my own words:** The clinic can only do as many procedures as its smallest limit allows, so `q = min(demand, staff, room, equipment)`. In the example, equipment limits us to 10 a month. Buying more equipment only raises this to 12, because then staff becomes the limit. Those 2 extra procedures don't pay back the 5,000 € purchase in 12 months, so buying (8,080 €) is worse than keeping (11,400 €). More equipment is not automatically better. Saved scenarios keep a copy of inputs and results, so later fee changes don't change them.

## 2026-10-10 — ADR-5, no live integrations (`806894a`)

- **Prompt:** ADR-5 on integrations.
- **Disposition:** Accepted.
- **What changed:** ADR-5: no live hospital/insurer integrations.
- **In my own words:** Connecting to real hospital or insurer systems needs real patient data, contracts, credentials and strong security, which is outside this assignment and risky if done badly. So the app uses fictional data and manual entry. Because the domains are separated, an integration could be added later without rewriting everything.

## 2026-10-12 — Final review against course notes

- **Prompt:** "Make sure the content is understandable and uses what we studied in the course notes."
- **Disposition:** Accepted.
- **What changed:** Found that Finance routes imported an Operations error, breaking ADR-2; added `CompletionError` in `application.py`. Added tests using course techniques (parametrize, monkeypatch, `pytest.raises(match=)`, HTTP happy/invalid/duplicate). Measured coverage (81.25% combined). Wrote `docs/report.md` and updated README, acceptance status and brief.
- **In my own words:** Finance must not import Operations, because if one day they become separate services they can't share Python code. The only place allowed to know both is `application.py`, so the error now comes from there. `DEMO_NOW` fixes the clock in tests: rules like "minimum notice" depend on the current time, and without a fixed clock a test could pass today and fail tomorrow (a flaky test). It makes the tests repeatable, the R in FIRST.

## 2026-10-12 — More intuitive app flow

- **Prompt:** "Suggest very good changes and improve the design and the flow so that it is more intuitive, based on my original project plan."
- **Disposition:** Accepted.
- **What changed:** Redesigned all four screens following the plan's §6 (warm off-white, navy, teal; coloured status labels; three option cards). Capacity now shows each session as a timeline with free gaps. Cancelling a booking shows which waiting patients can take the slot, with reasons. Bookings have "Mark as done", and invoices have their own payment form. Added `free_gaps`, `slot_candidates` and 5 tests (48 passed). The demo seed now uses "tomorrow" instead of a fixed date.
- **In my own words:** Before, the user had to type ID numbers and read formulas. Now the app guides the real job: see the free gaps, cancel if needed, pick a patient Medic says is eligible, mark the procedure as done, and record the payment. `free_gaps` walks through the bookings in time order and keeps the empty spaces between them. `slot_candidates` runs the same checks as a real booking (ready, available, notice, fits, no clash) for every waiting patient, but saves nothing. When I press Book, everything is checked again inside the transaction, so an old suggestion can't cause a double booking. The order is priority first, then who waited longest. Money never decides who gets the slot.

## 2026-10-12 — Final UI refinement and completion-date fix

- **Prompt:** "Read CURSOR_FINAL_UI_HANDOFF.md ... verify our exact commit allowance under the 40% rule and investigate the booking/completion-date inconsistency. Then implement the smallest coherent UI refinement using the supplied screenshots and HTML as references."
- **Disposition:** Accepted after checking it in the browser and with the tests.
- **What changed:** `complete_booking` now refuses a booking that has not started yet, a performed date that is not the booking's session date, and a due date before the performed date (3 regression tests). The seed adds one session from yesterday so the demo has a booking that can really be marked as done. The screens were renamed and restyled: Overview, Schedule, Collections, and Equipment plans under "Planning". Collections shows the completed procedure, patient and payment history before the payment form. Cancelled bookings go in a collapsed history, and past sessions show "unused" time instead of offering a match. 53 tests pass; combined coverage is 83.65%.
- **In my own words:** I could mark tomorrow's booking as done today and type any date. That made Finance believe a procedure happened when it hadn't, so the amount due appeared too early. Now the rule is in `application.py`, not only in the screen: even a hand-made POST is refused. "Mark as done" only appears after the start time, and the performed date is the session's own date. On the screens, I put the daily work first (Schedule) and the equipment comparison under Planning, because it is a manual what-if and is not calculated from the schedule. Collections only shows records for work that was really completed. That is the link between the two domains the user can see, while the code still keeps them separate.
