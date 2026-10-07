PRAGMA foreign_keys = ON;

-- Domain A: clinic operations
CREATE TABLE IF NOT EXISTS procedure_types (
    code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    turnover_minutes INTEGER NOT NULL CHECK (turnover_minutes >= 0)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_label TEXT NOT NULL,
    clinician_label TEXT NOT NULL,
    session_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    CHECK (start_time < end_time)
);

CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_ref TEXT NOT NULL,
    procedure_code TEXT NOT NULL REFERENCES procedure_types(code),
    priority INTEGER NOT NULL,
    requested_at TEXT NOT NULL,
    ready INTEGER NOT NULL CHECK (ready IN (0, 1)),
    available_from TEXT NOT NULL,
    available_to TEXT NOT NULL,
    minimum_notice_minutes INTEGER NOT NULL CHECK (minimum_notice_minutes >= 0)
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES requests(id),
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'cancelled', 'completed')),
    CHECK (start_time < end_time)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_booking_per_request
ON bookings(request_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS recovery_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cancelled_booking_id INTEGER NOT NULL REFERENCES bookings(id),
    candidate_request_id INTEGER NOT NULL REFERENCES requests(id),
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    proposed_start TEXT NOT NULL,
    proposed_end TEXT NOT NULL,
    reasons TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('suggested', 'accepted', 'rejected', 'stale')),
    created_at TEXT NOT NULL
);

-- Domain B: clinic finance (tables exist; money logic comes in later days)
CREATE TABLE IF NOT EXISTS fee_assumptions (
    procedure_code TEXT PRIMARY KEY REFERENCES procedure_types(code),
    expected_fee_cents INTEGER NOT NULL CHECK (expected_fee_cents >= 0),
    variable_cost_cents INTEGER NOT NULL CHECK (variable_cost_cents >= 0)
);

CREATE TABLE IF NOT EXISTS receivables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_booking_id INTEGER NOT NULL UNIQUE,
    procedure_code TEXT NOT NULL,
    performed_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    expected_fee_cents INTEGER NOT NULL CHECK (expected_fee_cents >= 0)
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receivable_id INTEGER NOT NULL REFERENCES receivables(id),
    payment_reference TEXT NOT NULL UNIQUE,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    paid_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS investment_scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    procedure_code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    model_version TEXT NOT NULL,
    input_snapshot_json TEXT NOT NULL,
    output_snapshot_json TEXT NOT NULL
);
