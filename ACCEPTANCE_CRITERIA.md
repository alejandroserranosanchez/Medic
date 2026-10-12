# Acceptance criteria — Medic (formerly CareQuanta)

**Written:** 2026-10-06 (specification, before approval) · **Status updated:** 2026-10-12  
**Professor approval:** Confirmed by student on 2026-10-07.

## Status at submission (2026-10-12, `53 passed`)

| Case | Status | Verified by (in `tests/`) |
|---|---|---|
| A1 Exact fit | Implemented | `test_booking_must_fit_session_including_turnover`, `test_vega_profile_block_is_30_not_raw_estimate` |
| A2 Turnover rejection | Implemented | `test_turnover_prevents_adjacent_booking` |
| A3 Half-open adjacency | Implemented | `test_half_open_touching_intervals_do_not_overlap` |
| A4 Room / clinician conflict | Implemented | `test_room_conflict_rejected`, `test_clinician_conflict_rejected`, `test_room_conflict_is_case_insensitive` |
| A5 Insufficient notice | Implemented for booking and replacement suggestions | `test_reject_insufficient_notice` |
| A6 Not ready | Implemented for booking and replacement suggestions | `test_reject_not_ready`, `test_candidates_ranked_with_reasons` |
| A7 Replacement ranking | Implemented: priority, then oldest request, then ID; eligible first | `test_candidates_ranked_with_reasons`, `test_cancel_redirects_to_replacement_suggestions` |
| A8 Duplicate active booking | Implemented | `test_duplicate_active_booking_rejected` |
| A9 Stale proposal acceptance | Partly: suggestions are not stored, and pressing Book re-checks everything inside the transaction; no dedicated stale-proposal test | `test_candidate_that_clashes_is_flagged` |
| A10 Cancel vs complete | Implemented; completion also refused before the booking starts, with a performed date other than the session date, or with a due date before it | `test_cancel_frees_capacity_for_new_booking`, `test_cancel_cannot_complete`, `test_complete_booking_creates_one_receivable`, `test_completing_same_booking_twice_creates_one_receivable`, `test_cannot_complete_booking_before_it_starts`, `test_completion_dates_must_match_the_booking`, `test_mark_as_done_before_start_is_refused` |
| B1 Partial then settle | Implemented | `test_payments_partial_duplicate_and_settle` |
| B2 Duplicate reference | Implemented | `test_payments_partial_duplicate_and_settle` |
| B3–B5 Overpaid / unpaid / zero fee | Implemented | `test_balance_status_labels` (parametrized) |
| B6 Fee snapshot | Implemented | `test_complete_booking_creates_one_receivable` |
| B7 Overdue flag | Implemented | `test_overdue_only_when_balance_positive_after_due_date` |
| C1–C2 Equipment / staff bottleneck | Implemented | `test_guide_example_numbers`, `test_staff_bottleneck_after_equipment_increase` |
| C3 Room bottleneck | Implemented | `test_room_bottleneck` |
| C4 Zero demand | Implemented | `test_zero_demand` |
| C5 Invalid inputs | Implemented; only months = 0 is tested | `test_invalid_months_rejected` |
| C6 Keep / buy / lease arithmetic | Implemented | `test_guide_example_numbers` |
| C7 Scenario persistence | Implemented | `test_save_and_reload_preserves_snapshots` |
| D1 Fresh `DATA_DIR` | Implemented | `test_port_and_data_dir_come_from_environment` |
| D2 Restart | Implemented | `test_seed_runs_once_only`, `test_session_persists_across_restart` |
| D3 One transaction | Implemented in code (`clinic/application.py`); rollback path **not directly tested** | — |
| D4 Bind / config | Implemented | `test_port_and_data_dir_come_from_environment` |

Euro input rule chosen at implementation: `euros_to_cents` uses `Decimal` and **rejects** more than 2 decimal places instead of rounding (`test_bad_euro_amount_is_rejected`).

The original specification below is kept unchanged as written on 2026-10-06.

---

These cases come from the product plan’s business rules. Inputs use fictional EUR amounts and clinic labels. Expected outcomes are the behaviours the future implementation and tests must satisfy.

---

## A. Capacity / operations

### A1. Exact fit booking interval

| | |
|---|---|
| **Given** | Session 09:00–12:00; procedure duration 30 min; turnover 10 min; free from 09:00 |
| **When** | Book request into 09:00–09:30 |
| **Then** | Booking accepted; occupied interval for conflict checks is [09:00, 09:40) |

### A2. Turnover-caused rejection

| | |
|---|---|
| **Given** | Existing booking occupies through turnover so next free start is after a candidate’s proposed end |
| **When** | Propose a slot whose occupied interval (including turnover) overlaps an existing occupied interval |
| **Then** | Rejected with an overlap/turnover reason; no booking written |

### A3. Half-open adjacency allowed

| | |
|---|---|
| **Given** | Booking A occupies [09:00, 09:40); next candidate wants start 09:40 |
| **When** | Check overlap using half-open [start, end) |
| **Then** | Allowed (end == next start is not overlap) |

### A4. Clinician or room conflict between sessions

| | |
|---|---|
| **Given** | Session in Room A with Clinician X overlapping another session that reuses Room A or Clinician X |
| **When** | Persist the second session |
| **Then** | Rejected; sessions that share room or clinician must not overlap |

### A5. Replacement — insufficient notice

| | |
|---|---|
| **Given** | Cancelled booking frees a slot; candidate request has `minimum_notice` not met by proposal time |
| **When** | Rank / accept replacement |
| **Then** | Candidate ineligible; reason cites insufficient notice |

### A6. Replacement — not ready

| | |
|---|---|
| **Given** | Candidate otherwise fits but readiness flag is false |
| **When** | Eligibility check |
| **Then** | Rejected with not-ready reason; suggestion does not reserve capacity |

### A7. Replacement — ranking order

| | |
|---|---|
| **Given** | Multiple eligible candidates |
| **When** | Rank for display / suggestion |
| **Then** | Order by clinician-entered priority (higher first), then oldest `requested_at`, then stable ID. Financial value must not affect order |

### A8. Duplicate active booking

| | |
|---|---|
| **Given** | Request already has an active booking |
| **When** | Attempt another active booking for the same request |
| **Then** | Rejected |

### A9. Stale proposal acceptance

| | |
|---|---|
| **Given** | Proposal was generated earlier; capacity changed (e.g. another booking accepted) so constraints no longer hold |
| **When** | Accept proposal inside a transaction with full revalidation |
| **Then** | Fail with clear explanation; must not overwrite a newer booking |

### A10. Cancellation vs completion

| | |
|---|---|
| **Given** | Active booking |
| **When** | Cancel |
| **Then** | Capacity freed; **no** receivable created |
| **When** | Complete |
| **Then** | Receivable created **exactly once** for that booking; repeated completion must not create a second receivable |

Every rejected candidate must show a reason. A suggested candidate does not reserve capacity until accepted.

---

## B. Payments / reconciliation

Money stored as integer euro cents. User decimal input parsed with `Decimal` and a documented rounding rule (to be fixed at implementation). No binary float for balances.

```text
paid_cents = sum(valid recorded payments for this receivable)
balance_cents = expected_fee_cents - paid_cents
```

### B1. Partial then settle

| | |
|---|---|
| **Given** | Receivable expected = 12000 cents (EUR 120.00) |
| **When** | Record payment reference `P1` for 9000 cents |
| **Then** | `paid_cents=9000`, `balance_cents=3000`, label **partial** |
| **When** | Record payment reference `P2` for 3000 cents |
| **Then** | `paid_cents=12000`, `balance_cents=0`, label **settled** |

### B2. Duplicate payment reference

| | |
|---|---|
| **Given** | Payment `P1` already recorded for 9000 cents |
| **When** | Submit the same payment reference `P1` again (any amount) |
| **Then** | No second payment counted; totals unchanged |

### B3. Overpaid

| | |
|---|---|
| **Given** | Expected 12000 cents |
| **When** | Valid payments total 13000 cents |
| **Then** | Label **overpaid**; `balance_cents=-1000` (10 EUR over) |

### B4. Unpaid

| | |
|---|---|
| **Given** | Expected > 0; no payments |
| **When** | Compute status |
| **Then** | Label **unpaid** |

### B5. Zero expected fee

| | |
|---|---|
| **Given** | Expected = 0; no payments |
| **When** | Compute status |
| **Then** | Label **settled** |

### B6. Fee snapshot immutability

| | |
|---|---|
| **Given** | Receivable created with `expected_fee_cents` snapshot at completion |
| **When** | Later edit to fee assumptions for that procedure code |
| **Then** | Historical receivable expectation unchanged |

### B7. Overdue flag

| | |
|---|---|
| **Given** | Positive balance and due date in the past |
| **When** | Compute flags |
| **Then** | Overdue is a **separate** flag; do not equate every partial with a confirmed insurer underpayment |

These EUR 120 / 90 / 30 / 130 figures are invented test amounts, not real clinical tariffs.

---

## C. Investment comparison

One procedure type per scenario. Options: **keep** current equipment, **buy** one candidate, **lease** that same candidate. Candidate monthly equipment capacity is the resulting total equipment capacity for that option.

```text
procedures_per_month(option) = min(demand, staffed_capacity,
                                    room_capacity, equipment_capacity(option))
monthly_expected_receipts = procedures_per_month * expected_receipt_per_procedure
monthly_variable_cost = procedures_per_month * variable_cost_per_procedure
horizon_net_cash = months * (monthly_expected_receipts
                            - monthly_variable_cost
                            - additional_monthly_staff_cost
                            - monthly_equipment_cash_cost)
                   - upfront_equipment_cash_cost
incremental_net_cash = horizon_net_cash(option) - horizon_net_cash(keep)
```

### C1. Equipment bottleneck

| | |
|---|---|
| **Given** | demand 30, staff 12, room 20, equipment 10 |
| **When** | Compute procedures/month |
| **Then** | 10; limiting factor = equipment |

### C2. Staff bottleneck after equipment increase

| | |
|---|---|
| **Given** | Same as C1 but equipment capacity becomes 40 |
| **When** | Compute procedures/month |
| **Then** | 12 (not 30 or 40); limiting factor = staff |

### C3. Room bottleneck

| | |
|---|---|
| **Given** | demand and staff high; room capacity lowest |
| **When** | Compute |
| **Then** | Throughput equals room capacity; explanation cites room |

### C4. Low / zero demand

| | |
|---|---|
| **Given** | demand 0 (or very low) |
| **When** | Compute |
| **Then** | procedures/month = 0 (or demand); buying equipment must not invent throughput |

### C5. Invalid horizon / negative inputs

| | |
|---|---|
| **Given** | months = 0, or any required input negative |
| **When** | Validate |
| **Then** | Rejected with clear validation error |

### C6. Keep / buy / lease cash arithmetic

| | |
|---|---|
| **Given** | Shared horizon and cost categories; buy has upfront purchase/setup; lease has lease setup + monthly lease; keep has current equipment capacity and costs |
| **When** | Compute horizon and incremental net cash |
| **Then** | Purchase is not double-counted as both upfront cash and depreciation; same horizon applied to all options |

### C7. Scenario persistence

| | |
|---|---|
| **Given** | Valid scenario saved with input snapshot and calculated output snapshot |
| **When** | Reload scenario |
| **Then** | Assumptions and outputs preserved; model assumptions stated (constant monthly demand, same-month collection; excludes tax, financing, residual value, discounting) |

Output is a simplified scenario estimate, not an accounting profit figure or investment recommendation.

---

## D. Cross-cutting (when foundation exists)

| ID | Case | Expected |
|---|---|---|
| D1 | Fresh `DATA_DIR` start | Schema created noninteractively; seed only on empty DB |
| D2 | Restart | Seed does not recreate deleted records or reset user changes |
| D3 | Completion + receivable | Same SQLite transaction; roll back both if either write fails |
| D4 | Bind / config | Listen `0.0.0.0`; `PORT` / `DATA_DIR` from env with documented defaults |
