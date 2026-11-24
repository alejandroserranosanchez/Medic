-- Finance schema version 004.
-- Makes the single-currency clinic convention explicit on receivables.
-- Existing rows keep their ids, booking references, dates, fees and payments.
-- New rows inherit EUR from the named default. This file does not rewrite 001–003.

IF COL_LENGTH(N'dbo.receivables', N'currency_code') IS NULL
BEGIN
    ALTER TABLE dbo.receivables
        ADD currency_code CHAR(3) NOT NULL
            CONSTRAINT DF_receivables_currency_code DEFAULT ('EUR')
            CONSTRAINT CK_receivables_currency_code CHECK (currency_code = 'EUR');
END
GO
