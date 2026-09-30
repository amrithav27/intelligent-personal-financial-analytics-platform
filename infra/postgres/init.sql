-- Phoenix Platform — PostgreSQL Schema
-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Users ────────────────────────────────────────────────────────────────────
CREATE TABLE users (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email              TEXT NOT NULL UNIQUE,
    email_hash         CHAR(64) NOT NULL UNIQUE,
    display_name       TEXT NOT NULL,
    password_hash      TEXT NOT NULL,
    role               TEXT NOT NULL DEFAULT 'USER' CHECK (role IN ('USER','ADVISOR','ADMIN')),
    encryption_key_ref TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMPTZ
);

-- ── Transaction Sources ───────────────────────────────────────────────────────
CREATE TYPE source_type AS ENUM ('BANK_API', 'CSV_UPLOAD', 'MANUAL_ENTRY');

CREATE TABLE transaction_sources (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type source_type NOT NULL,
    adapter_id  TEXT NOT NULL,
    label       TEXT NOT NULL,
    config      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Transactions ─────────────────────────────────────────────────────────────
CREATE TABLE transactions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_id        UUID REFERENCES transaction_sources(id),
    external_id      TEXT,
    amount           NUMERIC(18,4) NOT NULL,
    currency         CHAR(3) NOT NULL DEFAULT 'INR',
    merchant_name    TEXT,
    raw_description  TEXT,
    mcc_code         CHAR(4),
    ts               TIMESTAMPTZ NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_transactions_user_ts ON transactions(user_id, ts DESC);
CREATE INDEX idx_transactions_user_created ON transactions(user_id, created_at DESC);
CREATE UNIQUE INDEX idx_transactions_dedup ON transactions(user_id, external_id) WHERE external_id IS NOT NULL;

-- ── Categories ────────────────────────────────────────────────────────────────
CREATE TABLE categories (
    id        SERIAL PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    parent_id INT REFERENCES categories(id),
    icon      TEXT
);

-- Seed base categories
INSERT INTO categories (name, parent_id, icon) VALUES
  ('Groceries', NULL, '🛒'), ('Transportation', NULL, '🚗'), ('Utilities', NULL, '💡'),
  ('Entertainment', NULL, '🎬'), ('Healthcare', NULL, '🏥'), ('Dining', NULL, '🍽️'),
  ('Shopping', NULL, '🛍️'), ('Education', NULL, '📚'), ('Travel', NULL, '✈️'),
  ('Investments', NULL, '📈'), ('Rent/Housing', NULL, '🏠'), ('Insurance', NULL, '🛡️'),
  ('Personal Care', NULL, '💇'), ('Subscriptions', NULL, '📱'), ('Other', NULL, '📦');

-- ── Transaction Categories ────────────────────────────────────────────────────
CREATE TYPE categorization_method AS ENUM ('RULE_MCC', 'RULE_MERCHANT', 'RULE_KEYWORD', 'LLM', 'MANUAL', 'UNCATEGORIZED');

CREATE TABLE transaction_categories (
    transaction_id        UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    category_id           INT  NOT NULL REFERENCES categories(id),
    confidence            NUMERIC(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    method                categorization_method NOT NULL,
    categorizer_version   TEXT NOT NULL DEFAULT 'v1',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (transaction_id, created_at)
);

-- ── Financial Health Scores ───────────────────────────────────────────────────
CREATE TABLE financial_health_scores (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score              NUMERIC(5,2) NOT NULL CHECK (score >= 0 AND score <= 100),
    savings_rate       NUMERIC(5,4),
    dti_ratio          NUMERIC(5,4),
    spending_volatility NUMERIC(10,4),
    emergency_fund_ratio NUMERIC(5,4),
    computed_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_fhs_user_computed ON financial_health_scores(user_id, computed_at DESC);

-- ── Anomaly Alerts ────────────────────────────────────────────────────────────
CREATE TABLE anomaly_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    transaction_id  UUID REFERENCES transactions(id),
    category_id     INT  REFERENCES categories(id),
    z_score         NUMERIC(8,3) NOT NULL,
    description     TEXT NOT NULL,
    acknowledged_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_alerts_user_unread ON anomaly_alerts(user_id, acknowledged_at) WHERE acknowledged_at IS NULL;

-- ── Budgets ───────────────────────────────────────────────────────────────────
CREATE TABLE budgets (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id        INT  NOT NULL REFERENCES categories(id),
    month              DATE NOT NULL,
    recommended_amount NUMERIC(18,4) NOT NULL,
    limit_amount       NUMERIC(18,4) NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, category_id, month)
);

-- ── Audit Log ─────────────────────────────────────────────────────────────────
CREATE TABLE audit_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID,
    operation    TEXT NOT NULL,
    entity_type  TEXT NOT NULL,
    entity_id    TEXT,
    actor        TEXT NOT NULL,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_hash CHAR(64) NOT NULL
);

-- Trigger: prevent UPDATE/DELETE on audit_log
CREATE OR REPLACE FUNCTION audit_log_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is immutable: UPDATE/DELETE not permitted';
END;
$$;

CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();

-- ── Notification Preferences ─────────────────────────────────────────────────
CREATE TABLE notification_preferences (
    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id        INT  NOT NULL REFERENCES categories(id),
    email_enabled      BOOLEAN NOT NULL DEFAULT true,
    push_enabled       BOOLEAN NOT NULL DEFAULT true,
    websocket_enabled  BOOLEAN NOT NULL DEFAULT true,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, category_id)
);

-- Row-Level Security: users can only access their own data
-- Note: nullif(..., '') prevents a UUID cast error when app.current_user_id is not set
-- (current_setting with missing_ok=true returns '' when unset; nullif converts that to NULL;
--  NULL::UUID is NULL, so the USING clause evaluates to false → no rows, no crash)
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON transactions
  USING (user_id = nullif(current_setting('app.current_user_id', true), '')::UUID);

ALTER TABLE financial_health_scores ENABLE ROW LEVEL SECURITY;
CREATE POLICY fhs_user_isolation ON financial_health_scores
  USING (user_id = nullif(current_setting('app.current_user_id', true), '')::UUID);

ALTER TABLE anomaly_alerts ENABLE ROW LEVEL SECURITY;
CREATE POLICY alerts_user_isolation ON anomaly_alerts
  USING (user_id = nullif(current_setting('app.current_user_id', true), '')::UUID);

ALTER TABLE budgets ENABLE ROW LEVEL SECURITY;
CREATE POLICY budgets_user_isolation ON budgets
  USING (user_id = nullif(current_setting('app.current_user_id', true), '')::UUID);
