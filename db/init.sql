-- Local database creation only. This is not a schema migration.
-- One SQL Server instance holds two databases. Each login can own its own
-- database and is not given a user in the other one. Running this script again
-- creates nothing new and does not delete rows.
-- Passwords arrive from sqlcmd -v. They are not stored in this file.

IF DB_ID(N'operations') IS NULL
BEGIN
    CREATE DATABASE operations;
END
GO

IF DB_ID(N'finance') IS NULL
BEGIN
    CREATE DATABASE finance;
END
GO

IF SUSER_ID(N'operations_user') IS NULL
BEGIN
    CREATE LOGIN operations_user
        WITH PASSWORD = N'$(OPERATIONS_DB_PASSWORD)', CHECK_POLICY = ON;
END
ELSE
BEGIN
    ALTER LOGIN operations_user
        WITH PASSWORD = N'$(OPERATIONS_DB_PASSWORD)';
END
GO

IF SUSER_ID(N'finance_user') IS NULL
BEGIN
    CREATE LOGIN finance_user
        WITH PASSWORD = N'$(FINANCE_DB_PASSWORD)', CHECK_POLICY = ON;
END
ELSE
BEGIN
    ALTER LOGIN finance_user
        WITH PASSWORD = N'$(FINANCE_DB_PASSWORD)';
END
GO

USE operations;
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'operations_user')
BEGIN
    CREATE USER operations_user FOR LOGIN operations_user;
    ALTER ROLE db_owner ADD MEMBER operations_user;
END
GO

USE finance;
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'finance_user')
BEGIN
    CREATE USER finance_user FOR LOGIN finance_user;
    ALTER ROLE db_owner ADD MEMBER finance_user;
END
GO
