-- Operations schema version 003.
-- A booking can be completion_pending while Finance has not confirmed the receivable.
-- finance_receivable_id is the Finance id after a confirmed reply. It is not a foreign key.
-- Existing booking rows stay. This file does not rewrite 002_bookings.sql.

IF COL_LENGTH(N'dbo.bookings', N'finance_receivable_id') IS NULL
BEGIN
    ALTER TABLE dbo.bookings ADD finance_receivable_id INT NULL;
END
GO

IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_bookings_status'
      AND parent_object_id = OBJECT_ID(N'dbo.bookings')
      AND definition NOT LIKE N'%completion_pending%'
)
BEGIN
    ALTER TABLE dbo.bookings DROP CONSTRAINT CK_bookings_status;
    ALTER TABLE dbo.bookings ADD CONSTRAINT CK_bookings_status
        CHECK (status IN (N'active', N'cancelled', N'completed', N'completion_pending'));
END
GO
