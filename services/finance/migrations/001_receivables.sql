-- Finance schema version 001.
-- Creates the receivable table in the finance database only.
-- source_booking_id remembers which Operations booking this charge came from.
-- It is unique, and it is not a foreign key: Finance cannot see the bookings table.
-- This file does not insert rows. The runner records it and will not execute it again.

IF OBJECT_ID(N'dbo.receivables', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.receivables (
        id INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        source_booking_id INT NOT NULL,
        procedure_code NVARCHAR(20) NOT NULL,
        performed_date DATE NOT NULL,
        due_date DATE NOT NULL,
        expected_fee_cents INT NOT NULL,
        CONSTRAINT UQ_receivables_source_booking UNIQUE (source_booking_id),
        CONSTRAINT CK_receivables_fee CHECK (expected_fee_cents >= 0),
        CONSTRAINT CK_receivables_due_on_or_after_performed CHECK (due_date >= performed_date)
    );
END
GO
