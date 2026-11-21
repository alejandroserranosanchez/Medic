-- Finance schema version 003.
-- Moves the Assignment 1 fee catalogue into this database.
-- GASTRO is 12000 cents and COLONO is 18000 cents, the same values as clinic/seed.py.
-- There is no foreign key to Operations. This file does not change an existing fee row.

IF OBJECT_ID(N'dbo.fee_assumptions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.fee_assumptions (
        procedure_code NVARCHAR(20) NOT NULL PRIMARY KEY,
        expected_fee_cents INT NOT NULL,
        variable_cost_cents INT NOT NULL,
        CONSTRAINT CK_fee_expected CHECK (expected_fee_cents >= 0),
        CONSTRAINT CK_fee_variable CHECK (variable_cost_cents >= 0)
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.fee_assumptions WHERE procedure_code = N'GASTRO')
    INSERT INTO dbo.fee_assumptions (procedure_code, expected_fee_cents, variable_cost_cents)
    VALUES (N'GASTRO', 12000, 2500);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.fee_assumptions WHERE procedure_code = N'COLONO')
    INSERT INTO dbo.fee_assumptions (procedure_code, expected_fee_cents, variable_cost_cents)
    VALUES (N'COLONO', 18000, 4000);
GO
