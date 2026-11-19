-- Schema for the Video Game API (Azure SQL Database)
--
-- Run this once in the portal Query editor (signed in as the Entra admin).
-- It is safe to re-run: the table is only created if it does not exist.
-- The Function App's managed identity only needs db_datareader and db_datawriter;
-- it never creates or alters tables.

IF OBJECT_ID(N'dbo.games', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.games (
        -- The API generates a UUID for each game; it is stored as a real GUID
        id           UNIQUEIDENTIFIER NOT NULL
                     CONSTRAINT PK_games PRIMARY KEY,

        title        NVARCHAR(200)    NOT NULL,
        developer    NVARCHAR(200)    NOT NULL,
        releaseDate  DATE             NOT NULL,

        price        DECIMAL(10, 2)   NOT NULL
                     CONSTRAINT CK_games_price_nonnegative CHECK (price >= 0),

        -- Set by PATCH /api/games/validate, never by clients
        upcoming     BIT              NOT NULL
                     CONSTRAINT DF_games_upcoming DEFAULT 0,
        isFree       BIT              NOT NULL
                     CONSTRAINT DF_games_isFree DEFAULT 0,
        validatedOn  DATETIME2(0)     NULL,    -- UTC

        imageUrl     NVARCHAR(500)    NULL
    );
END;
GO

-- Check the result (should return the 9 columns above)
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'games'
ORDER BY ORDINAL_POSITION;
