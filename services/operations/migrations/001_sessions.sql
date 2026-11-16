-- Operations schema version 001.
-- Creates the tables for clinicians and sessions. Safe to inspect twice:
-- the migration runner records this file and will not execute it again.
-- This file does not insert rows and does not touch the finance database.

IF OBJECT_ID(N'dbo.clinicians', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.clinicians (
        id INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        display_name NVARCHAR(200) NOT NULL,
        CONSTRAINT UQ_clinicians_display_name UNIQUE (display_name)
    );
END
GO

IF OBJECT_ID(N'dbo.sessions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.sessions (
        id INT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
        room_label NVARCHAR(200) NOT NULL,
        clinician_id INT NOT NULL,
        clinician_label NVARCHAR(200) NOT NULL,
        session_date DATE NOT NULL,
        start_time NCHAR(5) NOT NULL,
        end_time NCHAR(5) NOT NULL,
        CONSTRAINT FK_sessions_clinician FOREIGN KEY (clinician_id) REFERENCES dbo.clinicians (id),
        CONSTRAINT CK_sessions_time CHECK (start_time < end_time)
    );
END
GO
