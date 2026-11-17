-- Operations schema version 002.
-- Adds the catalogue, waiting-list requests, and bookings.
-- Does not change clinicians or sessions, and does not insert rows.
-- The runner records this file, so a second boot does not execute it again.

IF OBJECT_ID(N'dbo.procedure_types', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.procedure_types (
        code NVARCHAR(20) NOT NULL PRIMARY KEY,
        display_name NVARCHAR(200) NOT NULL,
        duration_minutes INT NOT NULL,
        turnover_minutes INT NOT NULL,
        min_planning_minutes INT NOT NULL,
        CONSTRAINT CK_procedure_duration CHECK (duration_minutes > 0),
        CONSTRAINT CK_procedure_turnover CHECK (turnover_minutes >= 0),
        CONSTRAINT CK_procedure_minimum CHECK (min_planning_minutes > 0)
    );
END
GO

IF OBJECT_ID(N'dbo.clinician_procedure_profiles', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.clinician_procedure_profiles (
        id INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        clinician_id INT NOT NULL,
        procedure_code NVARCHAR(20) NOT NULL,
        estimated_duration_minutes INT NOT NULL,
        variability_minutes INT NOT NULL,
        estimate_origin NVARCHAR(200) NOT NULL,
        reviewed_on DATE NOT NULL,
        CONSTRAINT FK_profiles_clinician FOREIGN KEY (clinician_id) REFERENCES dbo.clinicians (id),
        CONSTRAINT FK_profiles_procedure FOREIGN KEY (procedure_code) REFERENCES dbo.procedure_types (code),
        CONSTRAINT UQ_profiles_clinician_procedure UNIQUE (clinician_id, procedure_code),
        CONSTRAINT CK_profiles_estimate CHECK (estimated_duration_minutes > 0),
        CONSTRAINT CK_profiles_variability CHECK (variability_minutes >= 0)
    );
END
GO

IF OBJECT_ID(N'dbo.requests', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.requests (
        id INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        patient_ref NVARCHAR(40) NOT NULL,
        procedure_code NVARCHAR(20) NOT NULL,
        priority INT NOT NULL,
        requested_at NVARCHAR(19) NOT NULL,
        ready BIT NOT NULL,
        available_from NVARCHAR(19) NOT NULL,
        available_to NVARCHAR(19) NOT NULL,
        minimum_notice_minutes INT NOT NULL,
        CONSTRAINT FK_requests_procedure FOREIGN KEY (procedure_code) REFERENCES dbo.procedure_types (code),
        CONSTRAINT CK_requests_notice CHECK (minimum_notice_minutes >= 0)
    );
END
GO

IF OBJECT_ID(N'dbo.bookings', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.bookings (
        id INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        request_id INT NOT NULL,
        session_id INT NOT NULL,
        start_time NCHAR(5) NOT NULL,
        end_time NCHAR(5) NOT NULL,
        status NVARCHAR(20) NOT NULL,
        profile_id INT NULL,
        timing_source NVARCHAR(20) NOT NULL,
        estimated_duration_minutes INT NOT NULL,
        variability_minutes INT NOT NULL,
        min_planning_minutes INT NOT NULL,
        planning_block_minutes INT NOT NULL,
        room_turnover_minutes INT NOT NULL,
        CONSTRAINT FK_bookings_request FOREIGN KEY (request_id) REFERENCES dbo.requests (id),
        CONSTRAINT FK_bookings_session FOREIGN KEY (session_id) REFERENCES dbo.sessions (id),
        CONSTRAINT FK_bookings_profile FOREIGN KEY (profile_id) REFERENCES dbo.clinician_procedure_profiles (id),
        CONSTRAINT CK_bookings_status CHECK (status IN (N'active', N'cancelled', N'completed')),
        CONSTRAINT CK_bookings_time CHECK (start_time < end_time)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'idx_one_active_booking_per_request' AND object_id = OBJECT_ID(N'dbo.bookings')
)
BEGIN
    CREATE UNIQUE INDEX idx_one_active_booking_per_request
        ON dbo.bookings (request_id)
        WHERE status = N'active';
END
GO
