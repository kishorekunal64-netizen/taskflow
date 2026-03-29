CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- User accounts
CREATE TYPE user_role   AS ENUM ('admin', 'analyst', 'viewer');
CREATE TYPE user_status AS ENUM ('active', 'locked');

CREATE TABLE IF NOT EXISTS users (
    user_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT         NOT NULL UNIQUE,
    password_hash TEXT         NOT NULL,
    role          user_role    NOT NULL,
    status        user_status  NOT NULL DEFAULT 'active',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_login    TIMESTAMPTZ
);

-- Activity log
CREATE TABLE IF NOT EXISTS user_activity (
    id          BIGSERIAL    PRIMARY KEY,
    user_id     UUID         NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    action      TEXT         NOT NULL,
    timestamp   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ip_address  TEXT         NOT NULL
);

-- Durable result store
CREATE TABLE IF NOT EXISTS analysis_results (
    date              TIMESTAMPTZ  PRIMARY KEY,
    market_sentiment  JSONB,
    sector_strength   JSONB,
    ai_signal         JSONB
);

CREATE TABLE IF NOT EXISTS sector_performance (
    date              TIMESTAMPTZ  NOT NULL,
    sector            TEXT         NOT NULL,
    momentum_score    FLOAT,
    relative_strength FLOAT,
    ranking           INT,
    PRIMARY KEY (date, sector)
);

CREATE TABLE IF NOT EXISTS institutional_flow (
    date      TIMESTAMPTZ  PRIMARY KEY,
    fii_buy   FLOAT,
    fii_sell  FLOAT,
    dii_buy   FLOAT,
    dii_sell  FLOAT,
    net_flow  FLOAT
);
