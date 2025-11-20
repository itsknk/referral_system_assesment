-- db/schema.sql

CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    username        TEXT UNIQUE,
    referral_code   VARCHAR(64) UNIQUE NOT NULL,
    referrer_id     BIGINT REFERENCES users(id),
    is_treasury     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT users_no_self_referral
        CHECK (referrer_id IS NULL OR referrer_id <> id)
);
CREATE INDEX idx_users_referrer_id ON users(referrer_id);

CREATE TABLE trades (
    id              BIGSERIAL PRIMARY KEY,
    trade_id        VARCHAR(128) NOT NULL,
    chain           VARCHAR(32)  NOT NULL,
    trader_id       BIGINT NOT NULL REFERENCES users(id),
    fee_token       VARCHAR(32) NOT NULL,
    fee_amount      NUMERIC(38, 6) NOT NULL,
    executed_at     TIMESTAMPTZ NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT trades_unique_trade_per_chain UNIQUE (trade_id, chain)
);
CREATE INDEX idx_trades_trader_id ON trades(trader_id);
CREATE INDEX idx_trades_executed_at ON trades(executed_at);

CREATE TABLE accrual_entries (
    id                  BIGSERIAL PRIMARY KEY,
    trade_id            BIGINT NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    chain               VARCHAR(32) NOT NULL,
    beneficiary_user_id BIGINT NOT NULL REFERENCES users(id),
    kind                VARCHAR(32) NOT NULL,
    token               VARCHAR(32) NOT NULL,
    amount              NUMERIC(38, 6) NOT NULL CHECK (amount >= 0),
    executed_at         TIMESTAMPTZ NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_accrual_entries_beneficiary ON accrual_entries(beneficiary_user_id);
CREATE INDEX idx_accrual_entries_trade ON accrual_entries(trade_id);
CREATE INDEX idx_accrual_entries_kind ON accrual_entries(kind);
CREATE INDEX idx_accrual_entries_executed_at ON accrual_entries(executed_at);

CREATE TABLE accrual_ledger (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id),
    kind            VARCHAR(32) NOT NULL,
    token           VARCHAR(32) NOT NULL,
    accrued_amount  NUMERIC(38, 6) NOT NULL DEFAULT 0,
    claimed_amount  NUMERIC(38, 6) NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT accrual_ledger_unique_key UNIQUE (user_id, kind, token)
);
CREATE INDEX idx_accrual_ledger_user ON accrual_ledger(user_id);

CREATE TABLE claim_events (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id),
    token           VARCHAR(32) NOT NULL,
    amount          NUMERIC(38, 6) NOT NULL CHECK (amount > 0),
    claim_type      VARCHAR(32) NOT NULL DEFAULT 'manual',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_claim_events_user ON claim_events(user_id);
CREATE INDEX idx_claim_events_created_at ON claim_events(created_at);

CREATE TABLE IF NOT EXISTS payout_batches (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    token       TEXT    NOT NULL,
    amount      NUMERIC(36, 6) NOT NULL,   -- total amount in this batch
    status      TEXT    NOT NULL DEFAULT 'pending', 
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payout_batches_user_token
    ON payout_batches (user_id, token);