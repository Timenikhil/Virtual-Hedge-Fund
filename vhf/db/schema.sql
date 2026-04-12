-- DDL statements to initialise the db
-- the transaction block ensures we don't get inconsistent dbs
BEGIN;
-- 1NF violated on purpose to support efficient querying and modification
-- while maintaining consistency, since individual strategies are not meaningful outside
-- portfolio and reweighting manually could cause normalisation errors
CREATE TABLE IF NOT EXISTS portfolios (PID INTEGER PRIMARY KEY AUTOINCREMENT,
                                       PNAME TEXT NOT NULL,
                                       WEIGHTS TEXT,
                                       SIDS TEXT NOT NULL,
                                       DATE TEXT NOT NULL,
                                       LIVE INTEGER NOT NULL,
                                       REBALANCER TEXT);

CREATE TABLE IF NOT EXISTS strategies (SID TEXT PRIMARY KEY,
                                       NAME TEXT NOT NULL,
                                       DESCRIPTION TEXT NOT NULL,
                                       CATEGORY TEXT NOT NULL,
                                       P0 INTEGER NOT NULL,
                                       P1 INTEGER NOT NULL,
                                       P2 INTEGER NOT NULL,
                                       P3 INTEGER NOT NULL,
                                       P4 INTEGER NOT NULL,
                                       P5 INTEGER NOT NULL,
                                       SOURCE TEXT);

-- violates 1NF for ease of retrieval
-- while ideally this should be SID,TIME,PRICES for the sake of simplicity, we assume
-- the PRICES series are aligned by time, and are comparable across the different Strategies
-- in production this should be stored in a different, cheaper DB, as price data can get very large
CREATE TABLE IF NOT EXISTS PRICES(SID TEXT PRIMARY KEY REFERENCES strategies(SID),
                                  PRICES TEXT);

-- portfolio weights history
CREATE TABLE IF NOT EXISTS phistory(PID INTEGER REFERENCES portfolios(PID),
                                    TIME INTEGER,-- unix time
                                    WEIGHTS TEXT,
                                    PRIMARY KEY (PID,TIME));

--QR
CREATE TABLE IF NOT EXISTS portfolio_accounts (PID INTEGER PRIMARY KEY,
                                               ACCOUNT TEXT NOT NULL,
                                               UNIQUE(ACCOUNT)
);

--  ranking table - designed to be modular, future work could extend this
--  by simply adding another column and computing the values
--  the columns are allowed to be null on purpose allowing users to only rank the strategy with the
--  algorithm they wish NULL rows are deprioritized during selection and ranking
--  Errors are precomputed to allow efficient ranking and deduplication
CREATE TABLE IF NOT EXISTS errors(SID TEXT PRIMARY KEY REFERENCES strategies(SID),
                                  ARIMA REAL,
                                  LSSVM REAL,
                                  EXPERT REAL,
                                  XAI REAL
                                 );

-- corr TABLE - absolute values are stored
-- stored in long form to reduce redundancy, every pair is stored exactly once
CREATE TABLE IF NOT EXISTS corr(SID1 TEXT REFERENCES strategies(SID),
                                SID2 TEXT REFERENCES strategies(SID),
                                corr REAL NOT NULL,
                                PRIMARY KEY (SID1, SID2));
END;
