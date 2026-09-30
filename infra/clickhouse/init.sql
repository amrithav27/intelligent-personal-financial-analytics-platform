-- Phoenix Platform — ClickHouse Analytical Schema
CREATE DATABASE IF NOT EXISTS phoenix;

-- FHS history: one row per computation
CREATE TABLE phoenix.financial_health_scores (
    user_id         UUID,
    score           Float32,
    savings_rate    Float32,
    dti_ratio       Float32,
    spending_volatility Float32,
    computed_at     DateTime
) ENGINE = ReplacingMergeTree(computed_at)
  PARTITION BY toYYYYMM(computed_at)
  ORDER BY (user_id, computed_at);

-- Monthly spending by category: pre-aggregated
CREATE TABLE phoenix.monthly_category_spending (
    user_id      UUID,
    category_id  Int32,
    category_name String,
    month        Date,
    total_amount Decimal(18,4),
    tx_count     Int32
) ENGINE = ReplacingMergeTree(month)
  PARTITION BY toYYYYMM(month)
  ORDER BY (user_id, month, category_id);

-- Individual transactions mirror (for trend queries without hitting PostgreSQL)
CREATE TABLE phoenix.transactions (
    id           UUID,
    user_id      UUID,
    amount       Decimal(18,4),
    currency     FixedString(3),
    category_id  Int32,
    ts           DateTime,
    created_at   DateTime
) ENGINE = MergeTree()
  PARTITION BY toYYYYMM(ts)
  ORDER BY (user_id, ts);
