-- Finance schema version 002.
-- Adds payments that belong to a receivable in this same database.
-- The foreign key stays inside Finance. It does not point at Operations.
-- This file does not insert rows. The runner records it and will not execute it again.

IF OBJECT_ID(N'dbo.payments', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.payments (
        id INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        receivable_id INT NOT NULL,
        payment_reference NVARCHAR(200) NOT NULL,
        amount_cents INT NOT NULL,
        paid_date DATE NOT NULL,
        CONSTRAINT FK_payments_receivable FOREIGN KEY (receivable_id) REFERENCES dbo.receivables (id),
        CONSTRAINT UQ_payments_reference UNIQUE (payment_reference),
        CONSTRAINT CK_payments_amount CHECK (amount_cents > 0)
    );
END
GO
