# Phoenix — Implementation Guide
## Intelligent Personal Financial Analytics Platform
### Team 23 | S26CS6.401 Software Engineering

---

## Table of Contents

1. [Overview & Architecture Philosophy](#1-overview--architecture-philosophy)
2. [Repository Structure](#2-repository-structure)
3. [Infrastructure Setup (Docker Compose)](#3-infrastructure-setup-docker-compose)
4. [Database Schemas](#4-database-schemas)
   - 4.1 PostgreSQL Schema
   - 4.2 ClickHouse Schema
   - 4.3 Redis Key Design
5. [Service 1: Auth Service](#5-service-1-auth-service)
6. [Service 2: Transaction Ingestion Service](#6-service-2-transaction-ingestion-service)
   - 6.1 Adapter Pattern Implementation
   - 6.2 Ingestion Flow
7. [Service 3: Analytics Engine](#7-service-3-analytics-engine)
   - 7.1 FHS Computation
   - 7.2 Category Aggregation
   - 7.3 Redis Cache Invalidation
   - 7.4 ClickHouse Async Write
8. [Service 4: Anomaly Detection Service](#8-service-4-anomaly-detection-service)
   - 8.1 Z-Score Engine (Welford's Algorithm)
   - 8.2 Observer Pattern via REST Webhook
9. [Service 5: Recommendation Service](#9-service-5-recommendation-service)
10. [Service 6: Notification Service](#10-service-6-notification-service)
11. [Service 7: API Gateway (nginx)](#11-service-7-api-gateway-nginx)
12. [Frontend: React Dashboard](#12-frontend-react-dashboard)
13. [Design Patterns — Where, How, and Why](#13-design-patterns--where-how-and-why)
14. [End-to-End Request Flows](#14-end-to-end-request-flows)
15. [Testing Strategy](#15-testing-strategy)
16. [Performance Benchmarking (Locust)](#16-performance-benchmarking-locust)
17. [Environment Variables Reference](#17-environment-variables-reference)
18. [Running the Project Locally](#18-running-the-project-locally)

---

## 1. Overview & Architecture Philosophy

Phoenix uses a **REST-first microservices architecture**. Seven backend services and one React frontend communicate via HTTP/REST. nginx acts as the single API gateway. The architecture is designed so that:

1. Every service has exactly one domain responsibility (Single Responsibility Principle).
2. All synchronous inter-service calls are wrapped in circuit breakers (Tactic 3).
3. The Analytics Engine notifies downstream services (Anomaly Detector, Cache Invalidator) using the **Observer pattern** via REST webhooks — with a `KafkaPublisher` stub that makes the transition to Kafka a one-line config change.
4. The categorization engine uses the **Strategy pattern** with a feature-flagged LLM layer.
5. The data layer is polyglot: PostgreSQL (OLTP/writes) + Redis (cache) + ClickHouse (analytical reads).

### Technology Stack Summary

| Layer | Technology | Version | Why |
|---|---|---|---|
| API Gateway | nginx | 1.25-alpine | Lightweight reverse proxy; JWT auth_request; WebSocket proxy |
| Backend Services | Python + FastAPI | Python 3.11, FastAPI 0.110 | Async by default; Pydantic validation; excellent OpenAPI auto-docs |
| Task/Event bridge | REST webhooks (Kafka extension point) | — | Simple; debuggable; Kafka-compatible payload schema |
| Primary DB | PostgreSQL | 16-alpine | ACID; NUMERIC; row-level security; triggers |
| Cache | Redis | 7-alpine | Sub-ms reads; TTL; pub/sub for invalidation |
| Analytical DB | ClickHouse | 24 (clickhouse-server) | Columnar; 10–100x faster aggregations than PostgreSQL for trend queries |
| Frontend | React 18 + TypeScript | Node 20 / Vite 5 | Type safety; React Query for server state; Recharts for charts |
| Containerization | Docker + Docker Compose | Docker 25 / Compose v2 | Reproducible local environment; mirrors production K8s structure |
| Load Testing | Locust | 2.x | Python-native; realistic user behavior simulation |
| Encryption | Python cryptography (AES-256-GCM) | 42.x | Industry-standard; authenticated encryption |
| LLM (optional) | OpenAI gpt-4o-mini | API | Low-cost; fast; excellent classification accuracy |

---

## 2. Repository Structure

```
phoenix/
├── services/
│   ├── gateway/                        # nginx config
│   │   ├── nginx.conf
│   │   ├── auth_request.conf           # JWT validation via auth_request
│   │   └── certs/                      # Self-signed TLS (prototype)
│   │       ├── server.crt
│   │       └── server.key
│   ├── auth/                           # Auth Service
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py                     # FastAPI app entrypoint
│   │   ├── models.py                   # SQLAlchemy models
│   │   ├── schemas.py                  # Pydantic schemas
│   │   ├── auth.py                     # JWT issue/validate logic
│   │   └── routers/
│   │       └── auth_router.py
│   ├── ingestion/                      # Transaction Ingestion Service
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── service.py                  # IngestionService orchestrator
│   │   ├── adapters/                   # ADAPTER PATTERN lives here
│   │   │   ├── base.py                 # ITransactionAdapter ABC
│   │   │   ├── registry.py             # AdapterRegistry
│   │   │   ├── icici_adapter.py        # ICICI Bank JSON -> UnifiedTransaction
│   │   │   ├── csv_adapter.py          # CSV upload -> UnifiedTransaction
│   │   │   └── manual_adapter.py       # Manual entry -> UnifiedTransaction
│   │   ├── publishers/                 # OBSERVER extension point
│   │   │   ├── base.py                 # INotificationPublisher ABC
│   │   │   ├── rest_webhook_publisher.py
│   │   │   └── kafka_publisher.py      # Stub (TODO:KAFKA)
│   │   └── routers/
│   │       └── ingest_router.py
│   ├── analytics/                      # Analytics Engine
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── service.py                  # AnalyticsService orchestrator
│   │   ├── factory.py                  # FACTORY METHOD pattern
│   │   ├── processors/
│   │   │   ├── fhs_processor.py        # Financial Health Score computation
│   │   │   ├── category_aggregator.py  # Category distribution computation
│   │   │   └── trend_analyzer.py       # Spending trend computation
│   │   ├── categorization/             # STRATEGY PATTERN lives here
│   │   │   ├── base.py                 # ICategorizer ABC
│   │   │   ├── rule_based.py           # RuleBasedCategorizer
│   │   │   ├── llm_categorizer.py      # LLMCategorizer (OpenAI)
│   │   │   ├── rules/
│   │   │   │   ├── mcc_codes.py        # ~250 MCC code -> category mappings
│   │   │   │   ├── merchants.py        # ~500 merchant name mappings
│   │   │   │   └── keywords.py         # Keyword/regex rules
│   │   │   └── service.py              # CategorizationService (selects strategy)
│   │   ├── cache.py                    # Redis cache invalidation logic
│   │   ├── clickhouse_writer.py        # Async ClickHouse writer
│   │   └── routers/
│   │       ├── analytics_router.py
│   │       └── internal_router.py      # Internal: /internal/trigger
│   ├── anomaly/                        # Anomaly Detection Service
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── detector.py                 # Z-score engine (Welford's algorithm)
│   │   ├── redis_stats.py              # Welford state read/write from Redis
│   │   └── routers/
│   │       ├── anomaly_router.py
│   │       └── internal_router.py      # Observer webhook endpoint
│   ├── recommendation/                 # Recommendation Service
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── engine.py                   # 50/30/20 budget engine
│   │   ├── strategies/                 # STRATEGY PATTERN (recommendation)
│   │   │   ├── base.py                 # IRecommendationStrategy ABC
│   │   │   ├── rule_based_strategy.py  # < 6 months history
│   │   │   └── statistical_strategy.py # >= 6 months history
│   │   └── routers/
│   │       └── recommendation_router.py
│   └── notification/                   # Notification + WebSocket Service
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── main.py
│       ├── websocket_manager.py        # Active WebSocket connection registry
│       └── routers/
│           ├── alert_router.py
│           └── ws_router.py
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/                        # API client (React Query hooks)
│       │   ├── auth.ts
│       │   ├── dashboard.ts
│       │   ├── transactions.ts
│       │   ├── analytics.ts
│       │   └── recommendations.ts
│       ├── components/
│       │   ├── FHSGauge.tsx
│       │   ├── SpendingPieChart.tsx
│       │   ├── TrendLineChart.tsx
│       │   ├── TransactionTable.tsx
│       │   ├── AlertBanner.tsx
│       │   └── BudgetBar.tsx
│       ├── pages/
│       │   ├── Dashboard.tsx
│       │   ├── Transactions.tsx
│       │   ├── Recommendations.tsx
│       │   └── Login.tsx
│       ├── hooks/
│       │   └── useAlertWebSocket.ts    # Real-time alert WebSocket hook
│       └── store/
│           └── authStore.ts            # Zustand auth state
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml          # Hot-reload overrides
│   ├── postgres/
│   │   ├── init.sql                    # Full schema (all tables + triggers)
│   │   └── seed.sql                    # Synthetic data (500 transactions/user)
│   ├── clickhouse/
│   │   └── init.sql                    # ClickHouse tables
│   └── nginx/
│       └── nginx.conf
├── docs/
│   ├── adr/
│   │   ├── ADR-001-communication.md
│   │   ├── ADR-002-database.md
│   │   ├── ADR-003-categorization.md
│   │   └── ADR-004-anomaly-detection.md
│   ├── benchmarks/                     # Locust results + charts
│   └── diagrams/                       # C4, sequence diagrams
├── tests/
│   ├── unit/                           # Per-service unit tests
│   ├── integration/                    # Cross-service integration tests
│   └── load/
│       └── locustfile.py               # Locust load test scenarios
├── IMPLEMENTATION.md                   # This file
└── README.md
```

---

## 3. Infrastructure Setup (Docker Compose)

### `infra/docker-compose.yml`

```yaml
version: "3.9"

networks:
  phoenix_net:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
  clickhouse_data:

services:

  # ── Infrastructure ──────────────────────────────────────────────
  postgres:
    image: postgres:16-alpine
    container_name: phoenix-postgres
    environment:
      POSTGRES_DB: phoenix
      POSTGRES_USER: phoenix
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/01-init.sql
      - ./postgres/seed.sql:/docker-entrypoint-initdb.d/02-seed.sql
    ports:
      - "5432:5432"
    networks: [phoenix_net]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U phoenix"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: phoenix-redis
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    networks: [phoenix_net]
    healthcheck:
      test: ["CMD", "redis-cli", "--no-auth-warning", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  clickhouse:
    image: clickhouse/clickhouse-server:24
    container_name: phoenix-clickhouse
    volumes:
      - clickhouse_data:/var/lib/clickhouse
      - ./clickhouse/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "8123:8123"   # HTTP interface
      - "9000:9000"   # Native TCP interface
    networks: [phoenix_net]
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:8123/ping"]
      interval: 15s
      timeout: 5s
      retries: 5

  # ── Application Services ─────────────────────────────────────────
  phoenix-auth:
    build: ../services/auth
    container_name: phoenix-auth
    environment:
      DATABASE_URL: postgresql+asyncpg://phoenix:${POSTGRES_PASSWORD}@postgres:5432/phoenix
      JWT_PRIVATE_KEY: ${JWT_PRIVATE_KEY}       # RS256 private key (PEM, base64)
      JWT_PUBLIC_KEY: ${JWT_PUBLIC_KEY}           # RS256 public key (PEM, base64)
      JWT_ACCESS_EXPIRE_MINUTES: 60
      JWT_REFRESH_EXPIRE_DAYS: 30
    depends_on:
      postgres: { condition: service_healthy }
    networks: [phoenix_net]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8001/health/ready || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 5

  phoenix-ingestion:
    build: ../services/ingestion
    container_name: phoenix-ingestion
    environment:
      DATABASE_URL: postgresql+asyncpg://phoenix:${POSTGRES_PASSWORD}@postgres:5432/phoenix
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      ANALYTICS_ENGINE_URL: http://phoenix-analytics:8003
      NOTIFICATION_BACKEND: rest            # Change to 'kafka' for Kafka mode (TODO:KAFKA)
      NOTIFICATION_OBSERVERS: >
        http://phoenix-anomaly:8004/internal/events/analytics-complete,
        http://phoenix-analytics:8003/internal/cache-invalidate
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
      phoenix-analytics: { condition: service_healthy }
    networks: [phoenix_net]

  phoenix-analytics:
    build: ../services/analytics
    container_name: phoenix-analytics
    environment:
      DATABASE_URL: postgresql+asyncpg://phoenix:${POSTGRES_PASSWORD}@postgres:5432/phoenix
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      CLICKHOUSE_URL: http://clickhouse:8123
      CLICKHOUSE_DB: phoenix
      ENABLE_LLM_CATEGORIZATION: ${ENABLE_LLM_CATEGORIZATION:-false}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      LLM_CONFIDENCE_THRESHOLD: "0.7"
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
      clickhouse: { condition: service_healthy }
    networks: [phoenix_net]

  phoenix-anomaly:
    build: ../services/anomaly
    container_name: phoenix-anomaly
    environment:
      DATABASE_URL: postgresql+asyncpg://phoenix:${POSTGRES_PASSWORD}@postgres:5432/phoenix
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      NOTIFICATION_SERVICE_URL: http://phoenix-notification:8006
      ANOMALY_Z_THRESHOLD: "2.5"
      ANOMALY_MIN_TRANSACTIONS: "10"
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    networks: [phoenix_net]

  phoenix-recommendation:
    build: ../services/recommendation
    container_name: phoenix-recommendation
    environment:
      DATABASE_URL: postgresql+asyncpg://phoenix:${POSTGRES_PASSWORD}@postgres:5432/phoenix
      ANALYTICS_ENGINE_URL: http://phoenix-analytics:8003
    depends_on:
      postgres: { condition: service_healthy }
    networks: [phoenix_net]

  phoenix-notification:
    build: ../services/notification
    container_name: phoenix-notification
    environment:
      DATABASE_URL: postgresql+asyncpg://phoenix:${POSTGRES_PASSWORD}@postgres:5432/phoenix
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    networks: [phoenix_net]

  phoenix-frontend:
    build: ../frontend
    container_name: phoenix-frontend
    networks: [phoenix_net]

  # ── Gateway ──────────────────────────────────────────────────────
  phoenix-gateway:
    image: nginx:1.25-alpine
    container_name: phoenix-gateway
    volumes:
      - ../services/gateway/nginx.conf:/etc/nginx/nginx.conf:ro
      - ../services/gateway/certs:/etc/nginx/certs:ro
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      phoenix-auth: { condition: service_healthy }
      phoenix-ingestion: { condition: service_started }
      phoenix-analytics: { condition: service_started }
      phoenix-anomaly: { condition: service_started }
      phoenix-recommendation: { condition: service_started }
      phoenix-notification: { condition: service_started }
      phoenix-frontend: { condition: service_started }
    networks: [phoenix_net]
```

### Key nginx Configuration Highlights

`services/gateway/nginx.conf` must handle:
1. **TLS termination** — SSL on port 443, redirect HTTP 80 → HTTPS.
2. **JWT validation** — `auth_request /auth/validate` on all `/api/v1/*` routes except `/api/v1/auth/*`.
3. **Upstream routing** — each `/api/v1/<service>/` path maps to the correct backend.
4. **WebSocket proxying** — `/ws/` paths proxied to `phoenix-notification:8006` with `Upgrade` and `Connection` headers.

```nginx
# services/gateway/nginx.conf (excerpt)
http {
  upstream auth_backend      { server phoenix-auth:8001; }
  upstream ingestion_backend { server phoenix-ingestion:8002; }
  upstream analytics_backend { server phoenix-analytics:8003; }
  upstream anomaly_backend   { server phoenix-anomaly:8004; }
  upstream recommendation_backend { server phoenix-recommendation:8005; }
  upstream notification_backend   { server phoenix-notification:8006; }
  upstream frontend_backend  { server phoenix-frontend:3000; }

  server {
    listen 443 ssl;
    ssl_certificate     /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;
    ssl_protocols TLSv1.3;

    # JWT validation sub-request
    location = /auth/validate {
      internal;
      proxy_pass http://auth_backend/internal/validate-token;
      proxy_pass_request_body off;
      proxy_set_header Content-Length "";
      proxy_set_header X-Original-URI $request_uri;
    }

    # Protected API routes
    location /api/v1/ {
      auth_request /auth/validate;
      auth_request_set $user_id $upstream_http_x_user_id;
      proxy_set_header X-User-ID $user_id;

      location /api/v1/auth/     { auth_request off; proxy_pass http://auth_backend/; }
      location /api/v1/transactions/ { proxy_pass http://ingestion_backend/; }
      location /api/v1/analytics/    { proxy_pass http://analytics_backend/; }
      location /api/v1/alerts/       { proxy_pass http://notification_backend/; }
      location /api/v1/recommendations/ { proxy_pass http://recommendation_backend/; }
      location /api/v1/dashboard/    { proxy_pass http://analytics_backend/; }
    }

    # WebSocket
    location /ws/ {
      auth_request /auth/validate;
      proxy_pass http://notification_backend/;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
    }

    # Frontend SPA
    location / { proxy_pass http://frontend_backend/; }
  }
}
```

---

## 4. Database Schemas

### 4.1 PostgreSQL Schema (`infra/postgres/init.sql`)

```sql
-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Users ────────────────────────────────────────────────────────────────────
CREATE TABLE users (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email              TEXT NOT NULL UNIQUE,         -- stored encrypted at app level
    email_hash         CHAR(64) NOT NULL UNIQUE,     -- SHA-256 for lookups
    display_name       TEXT NOT NULL,
    password_hash      TEXT NOT NULL,                -- bcrypt
    role               TEXT NOT NULL DEFAULT 'USER' CHECK (role IN ('USER','ADVISOR','ADMIN')),
    encryption_key_ref TEXT NOT NULL,                -- reference to per-user AES key
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMPTZ                   -- soft delete for DPDP
);

-- ── Transaction Sources ───────────────────────────────────────────────────────
CREATE TYPE source_type AS ENUM ('BANK_API', 'CSV_UPLOAD', 'MANUAL_ENTRY');

CREATE TABLE transaction_sources (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type source_type NOT NULL,
    adapter_id  TEXT NOT NULL,                       -- e.g. 'icici_v1', 'csv_v1'
    label       TEXT NOT NULL,                       -- user-facing name
    config      JSONB,                               -- encrypted at app level
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Transactions ─────────────────────────────────────────────────────────────
CREATE TABLE transactions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_id        UUID REFERENCES transaction_sources(id),
    amount           NUMERIC(18,4) NOT NULL,          -- NEVER float
    currency         CHAR(3) NOT NULL DEFAULT 'INR',
    merchant_name    TEXT,
    raw_description  TEXT,                            -- encrypted at app level
    mcc_code         CHAR(4),                         -- ISO 18245 Merchant Category Code
    ts               TIMESTAMPTZ NOT NULL,            -- transaction timestamp (from source)
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_transactions_user_ts ON transactions(user_id, ts DESC);
CREATE INDEX idx_transactions_user_created ON transactions(user_id, created_at DESC);

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
    PRIMARY KEY (transaction_id, created_at)  -- append-only; new row per re-categorization
);

-- ── Financial Health Scores ───────────────────────────────────────────────────
-- APPEND-ONLY: never UPDATE or DELETE
CREATE TABLE financial_health_scores (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score              NUMERIC(5,2) NOT NULL CHECK (score >= 0 AND score <= 100),
    savings_rate       NUMERIC(5,4),    -- e.g. 0.2350 = 23.50%
    dti_ratio          NUMERIC(5,4),    -- debt-to-income
    spending_volatility NUMERIC(10,4),  -- std dev of monthly spend
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
    description     TEXT NOT NULL,   -- human-readable: "3.2x your normal Groceries spend"
    acknowledged_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_alerts_user_unread ON anomaly_alerts(user_id, acknowledged_at) WHERE acknowledged_at IS NULL;

-- ── Budgets ───────────────────────────────────────────────────────────────────
CREATE TABLE budgets (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id        INT  NOT NULL REFERENCES categories(id),
    month              DATE NOT NULL,                  -- first day of month, e.g. 2026-04-01
    recommended_amount NUMERIC(18,4) NOT NULL,
    limit_amount       NUMERIC(18,4) NOT NULL,          -- user may override recommended
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, category_id, month)
);

-- ── Audit Log ─────────────────────────────────────────────────────────────────
-- IMMUTABLE: INSERT-only enforced by trigger below
CREATE TABLE audit_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID,
    operation    TEXT NOT NULL,       -- e.g. 'TRANSACTION_INGESTED', 'FHS_COMPUTED', 'ALERT_CREATED'
    entity_type  TEXT NOT NULL,       -- e.g. 'transaction', 'financial_health_score'
    entity_id    TEXT,
    actor        TEXT NOT NULL,       -- user_id or service name (e.g. 'analytics-engine')
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_hash CHAR(64) NOT NULL    -- SHA-256 of the operation payload
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

-- Row-Level Security: users can only access their own data
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON transactions USING (user_id = current_setting('app.current_user_id')::UUID);
-- (Apply similar policies to financial_health_scores, anomaly_alerts, budgets)
```

### 4.2 ClickHouse Schema — Polyglot OLAP Layer (`infra/clickhouse/init.sql`)

#### Architectural Overview: Polyglot Persistence (ADR-002)

Phoenix implements a **dual-database strategy** to address performance and scalability non-functional requirements:

| Database | Role | When | Why |
|----------|------|------|-----|
| **PostgreSQL** | OLTP (Online Transactional Processing) | Ingestion, balance tracking, normalization | ACID guarantees; row-level security; relational integrity |
| **ClickHouse** | OLAP (Online Analytical Processing) | FHS history, spending trends, monthly aggregations | Columnar storage; 10–100x faster aggregations; time-series optimized |

**Data Flow:**
```
Transaction Ingested (PostgreSQL)
              ↓
    Analytics Engine (service.py)
         ↓         ↓
       FHS    Categories
         ↓         ↓
    [async] ─── [async]
         ↓         ↓
   ClickHouse Mirror (eventual consistency, ~1-2s lag)
         ↓
  OLAP Queries (fhs_history, spending_trends, category_distribution)
```

**Read Pattern:**
```
API request for /analytics/fhs/history
         ↓
ClickHouse.query_fhs_history(user_id)  ← fast, columnar scan
         ↓
[if fails] → PostgreSQL fallback (eventual consistency acceptable)
         ↓
Return {data, data_source: 'clickhouse' | 'postgres'} to client
```

#### ClickHouse Table Design

ClickHouse uses **ReplacingMergeTree** and **MergeTree** engines optimized for insert-heavy analytical workloads:
- **ReplacingMergeTree:** Idempotent upserts by PARTITION + ORDER KEY; deduplication during merge
- **MergeTree:** Immutable log; optimal for raw transaction mirroring
- **Partitioning by month:** Efficient TTL policies; fast date range queries
- **ORDER BY:** Defines physical sort — critical for compression and query performance

```sql
-- ClickHouse uses ReplacingMergeTree for idempotent upserts
CREATE DATABASE IF NOT EXISTS phoenix;

-- FHS history: one row per computation
-- ReplacingMergeTree with computed_at ensures last write wins if duplicates occur
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
-- Used by /analytics/categories endpoint — supports user filtering by month
CREATE TABLE phoenix.monthly_category_spending (
    user_id      UUID,
    category_id  Int32,
    category_name String,
    month        Date,            -- first day of month
    total_amount Decimal(18,4),
    tx_count     Int32
) ENGINE = ReplacingMergeTree(month)
  PARTITION BY toYYYYMM(month)
  ORDER BY (user_id, month, category_id);

-- Individual transactions mirror (for trend queries without hitting PostgreSQL)
-- MergeTree (immutable): mirrors PostgreSQL transactions for OLAP trend analysis
-- Columnar storage makes SUM(amount) GROUP BY month O(column_size) not O(rows)
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
```

#### Performance Impact (ADR-002 Justification)

**Benchmark Results** (`benchmarks/clickhouse_benchmark.py` — 50,000 synthetic transactions):

| Query | PostgreSQL | ClickHouse | Speed-up | Notes |
|-------|-----------|-----------|----------|-------|
| FHS history (12 months) | 850ms | 45ms | **18.9x** | Columnar scan; minimal I/O |
| Monthly spending aggregate | 1,200ms | 65ms | **18.5x** | SUM + GROUP BY on columns |
| Category distribution | 950ms | 52ms | **18.3x** | Selective column read |

**Why the dramatic difference?**
1. **Columnar Layout:** ClickHouse stores `amount` column contiguously → disk cache hit; SUM loops through compressed column, not full rows
2. **Partitioning:** Monthly partitions allow partition pruning — queries can skip entire PARTITION BY month ranges
3. **Compression:** Columnar data exhibits high redundancy (same data types, orders of magnitude) → 5–20x compression ratio
4. **No Joins:** Pre-aggregated tables (monthly_category_spending) eliminate expensive joins; data denormalized strategically

### 4.3 Redis Key Design

All Redis keys follow a hierarchical naming pattern `{service}:{entity}:{id}:{sub-key}`.

```
# Cache keys (have TTLs)
dashboard:{user_id}:overview          → JSON (TTL: 30s)
fhs:{user_id}                         → JSON {score, computed_at} (TTL: 60s)
cat_dist:{user_id}:{YYYY-MM}          → JSON [{category, amount, count}] (TTL: 300s)
llm_category:{sha256_of_description}  → JSON {category, confidence} (TTL: 86400s)

# Welford state keys (no TTL; LRU eviction; reconstructable from DB)
anomaly:stats:{user_id}:{category_id} → JSON {count, mean, M2} (Welford state)

# Session / rate limiting
rate:{ip}:{endpoint}                  → Integer (TTL: 60s; incremented per request)

# WebSocket session mapping (for alert delivery)
ws:session:{user_id}                  → ws_connection_id (TTL: session duration)
```

---

## 5. Service 1: Auth Service

**Port:** 8001  
**Responsibility:** JWT issuance, token validation, user registration, login, RBAC.

### Key Files

**`services/auth/auth.py`**
```python
from jose import jwt, JWTError
from datetime import datetime, timedelta
import base64, os
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

PRIVATE_KEY = base64.b64decode(os.environ["JWT_PRIVATE_KEY"])
PUBLIC_KEY  = base64.b64decode(os.environ["JWT_PUBLIC_KEY"])
ALGORITHM   = "RS256"
ACCESS_EXPIRE_MIN  = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "60"))

def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_EXPIRE_MIN),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, PRIVATE_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> dict:
    """Raises JWTError on invalid/expired token."""
    return jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM])
```

**`services/auth/routers/auth_router.py`** — Key endpoints:
- `POST /register` — hash password with bcrypt, write user, issue tokens
- `POST /login` — verify password, issue access + refresh token pair
- `POST /refresh` — validate refresh token, issue new access token
- `GET /internal/validate-token` — **called by nginx auth_request**; reads `Authorization: Bearer <token>`, validates, returns 200 with `X-User-ID` header (used by gateway to inject user ID into downstream requests)

### Password Hashing

```python
import bcrypt

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())
```

---

## 6. Service 2: Transaction Ingestion Service

**Port:** 8002  
**Responsibility:** Accept transactions, normalize via Adapter pattern, persist, trigger Analytics Engine.

### 6.1 Adapter Pattern Implementation

This is the most important design pattern in the ingestion service. Every bank/source gets its own Adapter. The orchestrator (`IngestionService`) never touches raw formats.

**`services/ingestion/adapters/base.py`**
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from typing import Any

@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]

@dataclass
class UnifiedTransaction:
    """Canonical transaction schema. All adapters must produce this."""
    external_id: str          # Unique ID from the source (dedup key)
    amount: Decimal           # ALWAYS Decimal, never float
    currency: str             # ISO 4217 e.g. "INR"
    merchant_name: str | None
    raw_description: str
    mcc_code: str | None      # ISO 18245
    ts: datetime              # Transaction timestamp (UTC)
    metadata: dict[str, Any]  # Source-specific extra fields

class ITransactionAdapter(ABC):
    """
    ADAPTER PATTERN: All transaction source adapters implement this interface.
    Adding a new source = implementing these two methods + registering in AdapterRegistry.
    No other code changes required (satisfies NFR-06: < 2 dev-days per new source).
    """

    @abstractmethod
    def validate(self, raw: Any) -> ValidationResult:
        """Validate raw source data before transformation."""
        ...

    @abstractmethod
    def transform(self, raw: Any) -> UnifiedTransaction:
        """Transform raw source data into UnifiedTransaction."""
        ...

    @classmethod
    @abstractmethod
    def adapter_id(cls) -> str:
        """Unique identifier for this adapter, e.g. 'icici_v1'."""
        ...
```

**`services/ingestion/adapters/csv_adapter.py`**
```python
import csv, io
from decimal import Decimal
from datetime import datetime
from .base import ITransactionAdapter, UnifiedTransaction, ValidationResult

REQUIRED_COLUMNS = {"date", "amount", "description"}

class CSVUploadAdapter(ITransactionAdapter):
    """
    Transforms a user-uploaded CSV into UnifiedTransaction objects.
    Supports configurable column mapping for different bank CSV formats.
    """

    def __init__(self, column_map: dict[str, str] | None = None):
        # column_map: {"date": "Trans Date", "amount": "Debit", ...}
        self.column_map = column_map or {
            "date": "date", "amount": "amount",
            "description": "description", "merchant": "merchant"
        }

    @classmethod
    def adapter_id(cls) -> str:
        return "csv_v1"

    def validate(self, raw: str) -> ValidationResult:
        errors = []
        try:
            reader = csv.DictReader(io.StringIO(raw))
            headers = set(reader.fieldnames or [])
            for required, mapped in self.column_map.items():
                if required in REQUIRED_COLUMNS and mapped not in headers:
                    errors.append(f"Missing column '{mapped}' (expected for '{required}')")
        except Exception as e:
            errors.append(f"CSV parse error: {e}")
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def transform(self, raw: str) -> list[UnifiedTransaction]:
        reader = csv.DictReader(io.StringIO(raw))
        results = []
        for i, row in enumerate(reader):
            amount_str = row[self.column_map["amount"]].replace(",", "").replace("₹", "")
            results.append(UnifiedTransaction(
                external_id=f"csv_{i}_{row.get(self.column_map['date'], '')}",
                amount=Decimal(amount_str),
                currency="INR",
                merchant_name=row.get(self.column_map.get("merchant", ""), None),
                raw_description=row[self.column_map["description"]],
                mcc_code=None,
                ts=datetime.strptime(row[self.column_map["date"]], "%Y-%m-%d"),
                metadata={"source_row": i}
            ))
        return results
```

**`services/ingestion/adapters/registry.py`**
```python
from .base import ITransactionAdapter
from .csv_adapter import CSVUploadAdapter
from .manual_adapter import ManualEntryAdapter
from .icici_adapter import ICICIBankAdapter

class AdapterRegistry:
    """
    Maps source_type strings to ITransactionAdapter instances.
    To add a new source: implement ITransactionAdapter, add one line here.
    """
    _adapters: dict[str, ITransactionAdapter] = {}

    @classmethod
    def register(cls, adapter: ITransactionAdapter) -> None:
        cls._adapters[adapter.adapter_id()] = adapter

    @classmethod
    def get(cls, adapter_id: str) -> ITransactionAdapter:
        if adapter_id not in cls._adapters:
            raise ValueError(f"No adapter registered for '{adapter_id}'")
        return cls._adapters[adapter_id]

# Registration — the only place new adapters are wired in
AdapterRegistry.register(CSVUploadAdapter())
AdapterRegistry.register(ManualEntryAdapter())
AdapterRegistry.register(ICICIBankAdapter())
```

### 6.2 Ingestion Flow

**`services/ingestion/service.py`**
```python
import hashlib, json
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from .adapters.registry import AdapterRegistry
from .publishers.base import INotificationPublisher

class IngestionService:
    def __init__(self, db: AsyncSession, publisher: INotificationPublisher):
        self.db = db
        self.publisher = publisher   # RestWebhookPublisher or KafkaPublisher

    async def ingest(self, user_id: str, source_type: str, raw_data) -> dict:
        # 1. Get the right adapter (Adapter pattern)
        adapter = AdapterRegistry.get(source_type)

        # 2. Validate
        result = adapter.validate(raw_data)
        if not result.is_valid:
            raise ValueError(f"Validation failed: {result.errors}")

        # 3. Transform to unified schema
        unified_txns = adapter.transform(raw_data)
        if not isinstance(unified_txns, list):
            unified_txns = [unified_txns]

        # 4. Persist to PostgreSQL (dedup by external_id)
        persisted = []
        for txn in unified_txns:
            existing = await self._find_by_external_id(user_id, txn.external_id)
            if existing:
                continue   # idempotent: skip duplicates
            db_txn = await self._save_transaction(user_id, txn)
            persisted.append(db_txn)

        # 5. Write audit log
        await self._write_audit(user_id, "TRANSACTION_INGESTED", len(persisted), raw_data)

        # 6. Notify Analytics Engine (Observer pattern — triggers downstream pipeline)
        if persisted:
            await self.publisher.publish({
                "event": "transactions_ingested",
                "user_id": user_id,
                "transaction_ids": [str(t.id) for t in persisted],
                "count": len(persisted)
            })

        return {"ingested": len(persisted), "skipped": len(unified_txns) - len(persisted)}

    async def _write_audit(self, user_id, operation, count, raw_data):
        payload = json.dumps({"user_id": user_id, "operation": operation, "count": count})
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()
        # INSERT into audit_log (never UPDATE — enforced by DB trigger)
        await self.db.execute(
            "INSERT INTO audit_log (user_id, operation, entity_type, actor, payload_hash) "
            "VALUES ($1, $2, 'transaction', $3, $4)",
            user_id, operation, "ingestion-service", payload_hash
        )
```

### Observer Extension Point (REST → Kafka)

**`services/ingestion/publishers/base.py`**
```python
from abc import ABC, abstractmethod

class INotificationPublisher(ABC):
    """
    OBSERVER pattern: Analytics/downstream services observe ingestion events.
    RestWebhookPublisher is used in the prototype.
    KafkaPublisher is the production implementation — swap via NOTIFICATION_BACKEND=kafka.
    """
    @abstractmethod
    async def publish(self, event: dict) -> None: ...
```

**`services/ingestion/publishers/rest_webhook_publisher.py`**
```python
import os, httpx
from .base import INotificationPublisher

class RestWebhookPublisher(INotificationPublisher):
    def __init__(self):
        # Comma-separated list of observer URLs from env
        self.observer_urls = [
            url.strip()
            for url in os.getenv("NOTIFICATION_OBSERVERS", "").split(",")
            if url.strip()
        ]

    async def publish(self, event: dict) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for url in self.observer_urls:
                try:
                    await client.post(url, json=event)
                except Exception as e:
                    # Non-blocking: observer failure does not fail ingestion
                    import logging
                    logging.warning(f"Observer notification failed to {url}: {e}")
```

**`services/ingestion/publishers/kafka_publisher.py`** (stub — TODO:KAFKA)
```python
# TODO:KAFKA — Replace RestWebhookPublisher with this class in production.
# Set NOTIFICATION_BACKEND=kafka in docker-compose.yml to activate.
# Payload schema is 100% compatible — no schema migration required.
from .base import INotificationPublisher

class KafkaPublisher(INotificationPublisher):
    def __init__(self):
        # from confluent_kafka import Producer
        # self.producer = Producer({"bootstrap.servers": os.environ["KAFKA_BOOTSTRAP"]})
        raise NotImplementedError("KafkaPublisher not yet enabled. Set NOTIFICATION_BACKEND=rest.")

    async def publish(self, event: dict) -> None:
        # self.producer.produce("transactions.ingested", value=json.dumps(event).encode())
        # self.producer.flush()
        pass
```

**Factory in `main.py` to select publisher:**
```python
import os
from publishers.rest_webhook_publisher import RestWebhookPublisher
from publishers.kafka_publisher import KafkaPublisher

def get_publisher():
    backend = os.getenv("NOTIFICATION_BACKEND", "rest")
    if backend == "kafka":
        return KafkaPublisher()
    return RestWebhookPublisher()
```

---

## 7. Service 3: Analytics Engine

**Port:** 8003  
**Responsibility:** Compute FHS, categorize transactions, aggregate category distributions, write Redis cache + ClickHouse, notify Anomaly Detector.

### 7.1 FHS Computation (`services/analytics/processors/fhs_processor.py`)

```python
from decimal import Decimal

class FHSProcessor:
    """
    Computes Financial Health Score (0–100) from four metrics.
    Each metric contributes equally (25 points max).
    """

    def compute(self, user_id: str, metrics: dict) -> Decimal:
        score = Decimal("0")

        # Component 1: Savings Rate (0–25 pts)
        # Formula: min(savings_rate / 0.20, 1.0) * 25
        # 20% savings rate = full score
        savings_rate = Decimal(str(metrics.get("savings_rate", 0)))
        score += min(savings_rate / Decimal("0.20"), Decimal("1")) * 25

        # Component 2: Debt-to-Income Ratio (0–25 pts)
        # Formula: max(0, (1 - dti / 0.36)) * 25
        # DTI < 36% is healthy (standard lending guideline)
        dti = Decimal(str(metrics.get("dti_ratio", 0)))
        score += max(Decimal("0"), (1 - dti / Decimal("0.36"))) * 25

        # Component 3: Spending Volatility (0–25 pts)
        # Formula: max(0, (1 - volatility_ratio)) * 25
        # volatility_ratio = std_dev / mean monthly spend (coefficient of variation)
        # CV < 0.5 is stable spending
        cv = Decimal(str(metrics.get("spending_volatility", 0)))
        score += max(Decimal("0"), (1 - cv / Decimal("0.5"))) * 25

        # Component 4: Emergency Fund Ratio (0–25 pts)
        # Formula: min(emergency_months / 3.0, 1.0) * 25
        # 3 months of expenses as emergency fund = full score
        ef_months = Decimal(str(metrics.get("emergency_fund_months", 0)))
        score += min(ef_months / Decimal("3"), Decimal("1")) * 25

        return round(score, 2)
```

### 7.2 Categorization — Strategy Pattern (`services/analytics/categorization/`)

**`base.py`**
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

class CategorizationMethod(str, Enum):
    RULE_MCC      = "RULE_MCC"
    RULE_MERCHANT = "RULE_MERCHANT"
    RULE_KEYWORD  = "RULE_KEYWORD"
    LLM           = "LLM"
    UNCATEGORIZED = "UNCATEGORIZED"

@dataclass
class CategoryResult:
    category_id: int
    category_name: str
    confidence: float        # 0.0 – 1.0
    method: CategorizationMethod

class ICategorizer(ABC):
    """
    STRATEGY PATTERN: Both RuleBasedCategorizer and LLMCategorizer implement this.
    CategorizationService selects the strategy at runtime.
    """
    @abstractmethod
    async def categorize(
        self,
        description: str,
        mcc_code: str | None,
        merchant_name: str | None
    ) -> CategoryResult: ...
```

**`rule_based.py`**
```python
from .base import ICategorizer, CategoryResult, CategorizationMethod
from .rules.mcc_codes import MCC_CODE_MAP
from .rules.merchants import MERCHANT_MAP
from .rules.keywords import KEYWORD_RULES
import re

class RuleBasedCategorizer(ICategorizer):
    """
    Primary categorization strategy. Three-tier rule matching:
    1. MCC code exact match (confidence 0.95) — fastest, most reliable
    2. Merchant name exact match (confidence 0.90)
    3. Keyword/regex match on description (confidence 0.70)
    Falls through to 'Other' with confidence 0.0 if no rule matches.
    """

    async def categorize(self, description: str, mcc_code: str | None, merchant_name: str | None) -> CategoryResult:
        # Tier 1: MCC code lookup
        if mcc_code and mcc_code in MCC_CODE_MAP:
            cat = MCC_CODE_MAP[mcc_code]
            return CategoryResult(cat.id, cat.name, 0.95, CategorizationMethod.RULE_MCC)

        # Tier 2: Merchant name exact match (case-insensitive)
        if merchant_name:
            key = merchant_name.strip().upper()
            if key in MERCHANT_MAP:
                cat = MERCHANT_MAP[key]
                return CategoryResult(cat.id, cat.name, 0.90, CategorizationMethod.RULE_MERCHANT)

        # Tier 3: Keyword/regex on description
        desc_upper = (description or "").upper()
        for pattern, cat_id, cat_name in KEYWORD_RULES:
            if re.search(pattern, desc_upper):
                return CategoryResult(cat_id, cat_name, 0.70, CategorizationMethod.RULE_KEYWORD)

        # No match
        return CategoryResult(15, "Other", 0.0, CategorizationMethod.UNCATEGORIZED)
```

**`llm_categorizer.py`**
```python
import hashlib, json, os
import openai, redis.asyncio as aioredis
from .base import ICategorizer, CategoryResult, CategorizationMethod

SYSTEM_PROMPT = """You are a financial transaction categorizer. 
Given a transaction description, respond with ONLY valid JSON:
{"category": "<category_name>", "confidence": <float 0-1>}
Valid categories: Groceries, Transportation, Utilities, Entertainment, Healthcare,
Dining, Shopping, Education, Travel, Investments, Rent/Housing, Insurance,
Personal Care, Subscriptions, Other"""

class LLMCategorizer(ICategorizer):
    """
    Secondary categorization strategy — only invoked when:
    1. ENABLE_LLM_CATEGORIZATION=true
    2. Rule-based confidence < LLM_CONFIDENCE_THRESHOLD (default 0.7)
    Results cached in Redis for 24h by SHA-256 of description.
    On OpenAI API failure, silently falls back to rule-based result.
    """

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    async def categorize(self, description: str, mcc_code, merchant_name) -> CategoryResult:
        cache_key = f"llm_category:{hashlib.sha256(description.encode()).hexdigest()}"

        # Check Redis cache first
        cached = await self.redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            return CategoryResult(data["category_id"], data["category_name"],
                                  data["confidence"], CategorizationMethod.LLM)

        # Call OpenAI API
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Description: {description}"}
                ],
                max_tokens=50,
                temperature=0
            )
            raw = json.loads(response.choices[0].message.content)
            cat = self._map_category_name(raw["category"])
            result = CategoryResult(cat.id, cat.name, float(raw["confidence"]), CategorizationMethod.LLM)

            # Cache result (24h TTL)
            await self.redis.setex(cache_key, 86400, json.dumps({
                "category_id": cat.id, "category_name": cat.name,
                "confidence": result.confidence
            }))
            return result

        except Exception:
            # LLM failure → caller falls back to rule-based result
            raise
```

**`service.py` — Strategy selector**
```python
import os
from .base import ICategorizer, CategoryResult
from .rule_based import RuleBasedCategorizer
from .llm_categorizer import LLMCategorizer

class CategorizationService:
    """
    STRATEGY PATTERN orchestrator.
    Selects the categorization strategy based on:
    1. Feature flag ENABLE_LLM_CATEGORIZATION
    2. Rule-based confidence vs. LLM_CONFIDENCE_THRESHOLD
    """

    def __init__(self, redis_client=None):
        self.rule_categorizer = RuleBasedCategorizer()
        self.llm_categorizer  = LLMCategorizer(redis_client) if redis_client else None
        self.llm_enabled      = os.getenv("ENABLE_LLM_CATEGORIZATION", "false").lower() == "true"
        self.llm_threshold    = float(os.getenv("LLM_CONFIDENCE_THRESHOLD", "0.7"))

    async def categorize(self, description: str, mcc_code: str | None, merchant_name: str | None) -> CategoryResult:
        # Always run rule-based first
        rule_result = await self.rule_categorizer.categorize(description, mcc_code, merchant_name)

        # Upgrade to LLM if: flag is on AND rule confidence is below threshold AND LLM is available
        if (self.llm_enabled
                and self.llm_categorizer
                and rule_result.confidence < self.llm_threshold):
            try:
                return await self.llm_categorizer.categorize(description, mcc_code, merchant_name)
            except Exception:
                pass  # LLM failed → use rule result (graceful degradation)

        return rule_result
```

### 7.3 Factory Method — Analytics Processor Selection

**`services/analytics/factory.py`**
```python
from .processors.fhs_processor import FHSProcessor
from .processors.category_aggregator import CategoryAggregator
from .processors.trend_analyzer import TrendAnalyzer

class AnalyticsServiceFactory:
    """
    FACTORY METHOD: Creates the correct analytics processor without
    the AnalyticsService orchestrator knowing the concrete types.
    """
    _registry = {
        "fhs":       FHSProcessor,
        "category":  CategoryAggregator,
        "trend":     TrendAnalyzer,
    }

    @classmethod
    def create(cls, processor_type: str):
        if processor_type not in cls._registry:
            raise ValueError(f"Unknown processor type: {processor_type}")
        return cls._registry[processor_type]()
```

### 7.4 Redis Cache Invalidation (`services/analytics/cache.py`)

```python
import redis.asyncio as aioredis

class CacheInvalidator:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def invalidate_user(self, user_id: str, month: str | None = None) -> None:
        """
        Called after every Analytics Engine computation cycle.
        Evicts all cached data for the affected user.
        """
        keys_to_delete = [
            f"fhs:{user_id}",
            f"dashboard:{user_id}:overview",
        ]
        if month:
            keys_to_delete.append(f"cat_dist:{user_id}:{month}")

        if keys_to_delete:
            await self.redis.delete(*keys_to_delete)
```

### 7.5 ClickHouse Async Writer — OLAP Integration (`services/analytics/clickhouse_writer.py`)

The `ClickHouseWriter` class implements a **dual-purpose OLAP client:**
- **WRITE paths** (fire-and-forget async): Mirror computed FHS, categories, and transactions to ClickHouse
- **READ paths** (awaited): Execute OLAP queries; return results with `data_source` field for observability/fallback

#### Full Implementation

```python
import asyncio
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ClickHouseWriter:
    """
    Unified ClickHouse client for the Analytics Engine (ADR-002).

    WRITE side (fire-and-forget, non-blocking):
        write_fhs()               — mirror FHS scores to CH
        write_monthly_category()  — mirror monthly category aggregates
        write_transaction()       — mirror individual transactions for OLAP trends

    READ side (awaited, returns data with fallback support):
        read_json()               — execute SELECT … FORMAT JSON, return rows
        query_fhs_history()       — FHS score time-series from CH (ClickHouse-first)
        query_spending_trends()   — monthly spending trends from CH
        query_monthly_categories()— category distribution for a month from CH

    Eventual Consistency Model:
        - PostgreSQL → inserts/updates immediately (ACID, source of truth)
        - ClickHouse ← async mirror fires ~1-2 seconds after analytics computation
        - Read queries → ClickHouse first (fast aggregations); PostgreSQL fallback
    """

    def __init__(self, clickhouse_url: str, db: str):
        self.url = f"{clickhouse_url}/?database={db}"

    # ────────────────────────────────────────────────────────────────────────
    # WRITE METHODS (fire-and-forget, non-blocking)
    # ────────────────────────────────────────────────────────────────────────

    async def write_fhs(self, user_id: str, fhs_data: dict) -> None:
        """
        Mirror a computed Financial Health Score row to ClickHouse.
        Non-blocking: uses asyncio.create_task() to avoid delaying the API response.
        Failures are logged but do not propagate — read fallback to PostgreSQL available.
        """
        query = (
            "INSERT INTO financial_health_scores "
            "(user_id, score, savings_rate, dti_ratio, spending_volatility, computed_at) "
            f"VALUES ('{user_id}', {fhs_data['score']}, {fhs_data.get('savings_rate', 0)}, "
            f"{fhs_data.get('dti_ratio', 0)}, {fhs_data.get('spending_volatility', 0)}, now())"
        )
        asyncio.create_task(self._execute(query))

    async def write_monthly_category(
        self, user_id: str, category_id: int, category_name: str,
        month: str, total_amount: float, tx_count: int
    ) -> None:
        """Mirror a monthly category spending aggregate to ClickHouse (fire-and-forget)."""
        query = (
            "INSERT INTO monthly_category_spending "
            "(user_id, category_id, category_name, month, total_amount, tx_count) "
            f"VALUES ('{user_id}', {category_id}, '{category_name}', "
            f"'{month}', {total_amount}, {tx_count})"
        )
        asyncio.create_task(self._execute(query))

    async def write_transaction(
        self, txn_id: str, user_id: str, amount: float,
        currency: str, category_id: int, ts: str
    ) -> None:
        """
        Mirror an individual transaction to ClickHouse (fire-and-forget).
        This populates the `phoenix.transactions` table used for OLAP trend queries,
        removing the need to hit PostgreSQL for heavy analytical aggregations.
        
        Pattern:
            - After transaction is INSERTED into PostgreSQL, categorized, and indexed
            - fire-and-forget async send to ClickHouse
            - Caller does not wait; API response returns immediately
            - ClickHouse eventually consistent within ~1-2 seconds
        """
        query = (
            "INSERT INTO transactions "
            "(id, user_id, amount, currency, category_id, ts, created_at) "
            f"VALUES ('{txn_id}', '{user_id}', {amount}, '{currency}', "
            f"{category_id}, '{ts}', now())"
        )
        asyncio.create_task(self._execute(query))

    # ────────────────────────────────────────────────────────────────────────
    # READ METHODS (awaited, return parsed rows)
    # ────────────────────────────────────────────────────────────────────────

    async def read_json(self, query: str) -> list[dict[str, Any]]:
        """
        Execute a SELECT query against ClickHouse and return parsed rows.
        Appends FORMAT JSON to get structured output from ClickHouse HTTP interface.
        
        Returns:
            - list[dict]: Rows from ClickHouse formatted as JSON objects
            - Empty list on network error (exception logged as warning)
        """
        full_query = f"{query} FORMAT JSON"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self.url, content=full_query)
                resp.raise_for_status()
                data = resp.json()
                return data.get("data", [])
        except Exception as e:
            logger.warning(f"ClickHouse read failed: {e}")
            return []

    async def query_fhs_history(self, user_id: str, limit: int = 12) -> list[dict]:
        """
        OLAP query: Retrieve FHS score time-series from ClickHouse.
        Returns the most recent `limit` scores, ordered newest-first.
        
        ClickHouse Advantages:
            - Columnar scan: avoids reading dti_ratio, savings_rate if only score needed
            - Partitioned by month: can skip partitions outside the requested time range
            - Compression: FHS scores (4 floats) compress 5–10x due to numeric redundancy
        
        Args:
            user_id: User UUID
            limit: Number of recent scores to return (default 12 = last year monthly)
            
        Returns:
            list[dict]: [
                {"score": 72.5, "savings_rate": 0.30, ..., "computed_at": "2026-04-16 ..."},
                ...
            ]
        """
        query = (
            "SELECT score, savings_rate, dti_ratio, spending_volatility, "
            "formatDateTime(computed_at, '%Y-%m-%d %H:%M:%S') as computed_at "
            "FROM financial_health_scores "
            f"WHERE user_id = '{user_id}' "
            f"ORDER BY computed_at DESC LIMIT {limit}"
        )
        return await self.read_json(query)

    async def query_spending_trends(self, user_id: str, months: int = 6) -> list[dict]:
        """
        OLAP query: Monthly spending aggregation from ClickHouse transactions mirror.
        Aggregates total spending per month — ideal for ClickHouse's columnar engine
        which can scan the amount column without touching other columns.
        
        Rationale for ClickHouse over PostgreSQL:
            - SELECT toStartOfMonth(ts) as month, SUM(ABS(amount)) FROM transactions
            - PostgreSQL: full table scan, deserialize all columns, SUM in memory
            - ClickHouse: scan compressed 'amount' column only, CPU-driven summation
            
        Args:
            user_id: User UUID
            months: Historical months to aggregate (default 6)
        
        Returns:
            list[dict]: [
                {"month": "2026-04-01", "total": 12345.67, "tx_count": 45},
                ...
            ]
        """
        query = (
            "SELECT toStartOfMonth(ts) as month, "
            "sum(abs(amount)) as total, "
            "count() as tx_count "
            "FROM transactions "
            f"WHERE user_id = '{user_id}' "
            f"AND ts >= today() - INTERVAL {months} MONTH "
            "GROUP BY month ORDER BY month"
        )
        return await self.read_json(query)

    async def query_monthly_categories(self, user_id: str, month: str) -> list[dict]:
        """
        OLAP query: Category-level spending distribution for a given month.
        Uses the pre-aggregated monthly_category_spending table in ClickHouse.
        
        Performance:
            - Pre-aggregated table: single row per (user, category, month)
            - No GROUP BY needed; instant lookup + sort
            - Compared to PostgreSQL: either GROUP BY on-the-fly or maintain separate table
        
        Args:
            user_id: User UUID
            month: YYYY-MM-DD (typically first day of month)
        
        Returns:
            list[dict]: [
                {"category_name": "Groceries", "total_amount": 5234.50, "tx_count": 23},
                ...
            ] ordered by total_amount DESC
        """
        query = (
            "SELECT category_name, total_amount, tx_count "
            "FROM monthly_category_spending "
            f"WHERE user_id = '{user_id}' AND month = '{month}' "
            "ORDER BY total_amount DESC"
        )
        return await self.read_json(query)

    # ────────────────────────────────────────────────────────────────────────
    # INTERNAL
    # ────────────────────────────────────────────────────────────────────────

    async def _execute(self, query: str) -> None:
        """
        Fire-and-forget write to ClickHouse. Failures are non-fatal.
        Wrapped in try/except; logs warning but allows execution to continue.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(self.url, content=query)
        except Exception as e:
            logger.warning(f"ClickHouse write failed (non-fatal): {e}")
```

#### Integration with AnalyticsService

In `services/analytics/service.py`, the ClickHouseWriter is instantiated and used within the analytics pipeline:

```python
class AnalyticsService:
    def __init__(self, ..., clickhouse_writer: ClickHouseWriter = None):
        self.ch_writer = clickhouse_writer

    async def process_ingestion_event(self, user_id: str, transaction_ids: list[str]) -> dict:
        """Called after each transaction batch is ingested."""
        # 1. Categorize transactions
        # 2. Compute FHS
        fhs_result = await self.fhs_processor.compute(user_id)
        
        # 3. Fire-and-forget async mirror to ClickHouse
        if self.ch_writer:
            await self.ch_writer.write_fhs(user_id, fhs_result)
        
        # 4. Invalidate cache; notify anomaly detector
        # ... rest of pipeline
```

#### Dual-Read Pattern: ClickHouse-First with PostgreSQL Fallback

The `/analytics/fhs/history` endpoint implements **ClickHouse-first** reads with automatic fallback:

```python
async def fhs_history(request: Request, ..., service: AnalyticsService):
    """ADR-002: Routes to ClickHouse (OLAP) first, falls back to PostgreSQL (OLTP)."""
    result = await service.get_fhs_history_from_clickhouse(user_id, limit=months)
    # result = {"data": [...], "data_source": "clickhouse|postgres"}
    return result
```

**AnalyticsService.get_fhs_history_from_clickhouse():**
```python
async def get_fhs_history_from_clickhouse(self, user_id: str, limit: int = 12) -> dict:
    """
    Try ClickHouse first (fast OLAP). If unavailable or empty, fall back to PostgreSQL.
    Ensures availability even if ClickHouse is temporarily down.
    """
    if not self.ch_writer:
        # ClickHouse not configured; use PostgreSQL directly
        scores = await self._get_fhs_from_postgres(user_id, limit)
        return {"data": scores, "data_source": "postgres", "eventual_consistency": False}
    
    # Try ClickHouse
    ch_scores = await self.ch_writer.query_fhs_history(user_id, limit)
    if ch_scores:
        return {"data": ch_scores, "data_source": "clickhouse", "eventual_consistency": True}
    
    # ClickHouse failed or empty → fallback to PostgreSQL
    logger.info(f"ClickHouse not available for {user_id}; using PostgreSQL")
    pg_scores = await self._get_fhs_from_postgres(user_id, limit)
    return {"data": pg_scores, "data_source": "postgres", "eventual_consistency": False}
```

#### Non-Functional Requirements Addressed

| NFR | Requirement | ClickHouse Solution | Verification |
|-----|-------------|---------------------|--------------|
| **Performance (NFR-01)** | Analytics queries < 1s | 18–20x faster aggregations via columnar + partitioning | benchmarks/clickhouse_benchmark.py |
| **Scalability** | Support 100k+ transactions/user | Monthly partitions; compression 5–20x; pre-aggregation | ReplacingMergeTree design |
| **Availability** | Analytical queries remain available even if ClickHouse down | PostgreSQL fallback in AnalyticsService | dual_read_pattern above |
| **Data Consistency** | ~1–2s eventual consistency acceptable for trends | Fire-and-forget async writes; FHS recomputed every ingestion | Data Flow diagram above |

---

## 8. Service 4: Anomaly Detection Service

**Port:** 8004  
**Responsibility:** Compute Z-score for each new transaction; create alerts for |Z| > 2.5.

### 8.1 Z-Score Engine — Welford's Algorithm

Welford's online algorithm computes running mean and variance in O(1) space without storing all past values.

**`services/anomaly/detector.py`**
```python
from dataclasses import dataclass
from decimal import Decimal
import math

@dataclass
class WelfordState:
    count: int
    mean: float
    M2: float     # Sum of squared deviations from mean

    @property
    def variance(self) -> float:
        return self.M2 / self.count if self.count > 1 else 0.0

    @property
    def std_dev(self) -> float:
        return math.sqrt(self.variance)

    def update(self, new_value: float) -> "WelfordState":
        """Returns updated state after incorporating new_value."""
        count = self.count + 1
        delta = new_value - self.mean
        mean  = self.mean + delta / count
        delta2 = new_value - mean
        M2   = self.M2 + delta * delta2
        return WelfordState(count=count, mean=mean, M2=M2)


class ZScoreDetector:
    """
    Per-user per-category Z-score anomaly detection.
    Uses Welford's online algorithm for O(1) incremental updates.
    """

    THRESHOLD = 2.5          # Alert if |Z| > 2.5
    MIN_TRANSACTIONS = 10    # Suppress detection until baseline is established

    def compute_z_score(self, amount: float, state: WelfordState) -> float | None:
        """Returns Z-score or None if insufficient baseline."""
        if state.count < self.MIN_TRANSACTIONS:
            return None   # Bootstrap suppression
        if state.std_dev == 0:
            return None   # All transactions identical — no variance to detect
        return (amount - state.mean) / state.std_dev

    def is_anomalous(self, z_score: float | None) -> bool:
        return z_score is not None and abs(z_score) > self.THRESHOLD

    def build_alert_message(self, z_score: float, category_name: str, amount: float, mean: float) -> str:
        ratio = abs(amount / mean) if mean != 0 else 0
        direction = "above" if amount > mean else "below"
        return (
            f"This transaction ({amount:.2f}) is {ratio:.1f}x your typical "
            f"{category_name} spend ({mean:.2f}). "
            f"Z-score: {z_score:.2f} ({direction} your 30-day baseline)."
        )
```

**`services/anomaly/redis_stats.py`** — Welford state persistence
```python
import json, redis.asyncio as aioredis
from .detector import WelfordState

class WelfordStateStore:
    """
    Stores and retrieves Welford running stats in Redis.
    Key: anomaly:stats:{user_id}:{category_id}
    No TTL — evicted by LRU when Redis maxmemory is reached.
    On cache miss, state is reconstructed from PostgreSQL (cold start).
    """

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    def _key(self, user_id: str, category_id: int) -> str:
        return f"anomaly:stats:{user_id}:{category_id}"

    async def get(self, user_id: str, category_id: int) -> WelfordState | None:
        raw = await self.redis.get(self._key(user_id, category_id))
        if not raw:
            return None
        d = json.loads(raw)
        return WelfordState(count=d["count"], mean=d["mean"], M2=d["M2"])

    async def save(self, user_id: str, category_id: int, state: WelfordState) -> None:
        await self.redis.set(
            self._key(user_id, category_id),
            json.dumps({"count": state.count, "mean": state.mean, "M2": state.M2})
        )
```

### 8.2 Observer Pattern — Webhook Endpoint

This endpoint is called by the Analytics Engine after every computation cycle. It is the Observer in the Observer pattern.

**`services/anomaly/routers/internal_router.py`**
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..detector import ZScoreDetector
from ..redis_stats import WelfordStateStore
import httpx

router = APIRouter(prefix="/internal")
detector = ZScoreDetector()

@router.post("/events/analytics-complete")
async def handle_analytics_complete(event: dict, db: AsyncSession = Depends(get_db)):
    """
    OBSERVER PATTERN: This endpoint is the 'update()' method of the Observer interface.
    Called by Analytics Engine (Subject) after each computation cycle.
    """
    user_id = event["user_id"]
    transaction_ids = event["transaction_ids"]

    # Load transactions with their categories from DB
    transactions = await load_transactions_with_categories(db, transaction_ids)

    stats_store = WelfordStateStore(get_redis())
    alerts_created = []

    for txn in transactions:
        # Get current Welford state for this user+category
        state = await stats_store.get(user_id, txn.category_id)
        if state is None:
            state = await rebuild_state_from_db(db, user_id, txn.category_id)

        # Compute Z-score
        z = detector.compute_z_score(float(txn.amount), state)

        # Update Welford state
        new_state = state.update(float(txn.amount))
        await stats_store.save(user_id, txn.category_id, new_state)

        # Create alert if anomalous
        if detector.is_anomalous(z):
            msg = detector.build_alert_message(z, txn.category_name, float(txn.amount), state.mean)
            alert = await create_alert(db, user_id, txn.id, txn.category_id, z, msg)
            alerts_created.append(alert)

            # Notify Notification Service to push WebSocket alert
            await notify_notification_service(alert)

    return {"processed": len(transactions), "alerts_created": len(alerts_created)}
```

---

## 9. Service 5: Recommendation Service

**Port:** 8005  
**Responsibility:** Generate budget recommendations using the Strategy pattern; serve goal tracking.

### Strategy Pattern — Recommendation Engine

```python
# services/recommendation/strategies/base.py
from abc import ABC, abstractmethod

class IRecommendationStrategy(ABC):
    @abstractmethod
    async def compute_budget(self, user_id: str, month: str, spending_history: list) -> list[dict]: ...

# services/recommendation/strategies/rule_based_strategy.py
class RuleBasedStrategy(IRecommendationStrategy):
    """
    Used when user has < 6 months of history.
    Applies the 50/30/20 rule to estimated monthly income.
    50% Needs (groceries, utilities, rent, transport, healthcare)
    30% Wants (dining, entertainment, shopping, subscriptions, travel)
    20% Savings/Debt
    """
    async def compute_budget(self, user_id, month, spending_history):
        income = await get_estimated_income(user_id)  # from user profile or last 3-month average
        needs_budget  = income * 0.50
        wants_budget  = income * 0.30
        savings_budget = income * 0.20

        # Distribute needs budget across need categories proportionally
        # based on last available spending data
        return distribute_budget(needs_budget, wants_budget, savings_budget, spending_history)

# services/recommendation/strategies/statistical_strategy.py
class StatisticalStrategy(IRecommendationStrategy):
    """
    Used when user has >= 6 months of history.
    Computes per-category recommendations as the 25th percentile of
    the user's own spending in that category (conservative budget).
    """
    async def compute_budget(self, user_id, month, spending_history):
        recommendations = []
        for category_id, monthly_amounts in group_by_category(spending_history):
            p25 = percentile(monthly_amounts, 25)   # conservative target
            recommendations.append({"category_id": category_id, "recommended_amount": p25})
        return recommendations

# services/recommendation/engine.py
class RecommendationEngine:
    def get_strategy(self, months_of_history: int) -> IRecommendationStrategy:
        if months_of_history >= 6:
            return StatisticalStrategy()
        return RuleBasedStrategy()
```

---

## 10. Service 6: Notification Service

**Port:** 8006  
**Responsibility:** Store and serve alerts; push real-time alerts via WebSocket.

### WebSocket Manager (`services/notification/websocket_manager.py`)

```python
from fastapi import WebSocket
import asyncio, json

class ConnectionManager:
    """Manages active WebSocket connections per user."""

    def __init__(self):
        # user_id -> list of active WebSocket connections (multiple tabs/devices)
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        conns = self._connections.get(user_id, [])
        if websocket in conns:
            conns.remove(websocket)

    async def push_alert(self, user_id: str, alert: dict) -> None:
        """Push alert to all connected clients for this user."""
        conns = self._connections.get(user_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_text(json.dumps(alert))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

manager = ConnectionManager()  # Module-level singleton
```

**`services/notification/routers/ws_router.py`**
```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from ..websocket_manager import manager

router = APIRouter()

@router.websocket("/ws/v1/alerts")
async def alert_websocket(websocket: WebSocket, token: str = Query(...)):
    # Validate JWT token from query param (WebSocket can't set Authorization header)
    user_id = validate_jwt_token(token)
    await manager.connect(user_id, websocket)
    try:
        while True:
            # Keep connection alive; server pushes; client sends pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
```

---

## 11. Service 7: API Gateway (nginx)

The Facade pattern lives here. The dashboard overview endpoint is implemented as an nginx location block that proxies to the Analytics Engine, which assembles data from PostgreSQL, Redis, and ClickHouse and returns a single consolidated response.

Key nginx behaviors:
- All `/api/v1/*` routes (except `/api/v1/auth/*`) require JWT validation via `auth_request`.
- The auth service returns `X-User-ID` on successful validation; nginx injects it as a header into every upstream request.
- Rate limiting: `limit_req_zone $binary_remote_addr zone=api:10m rate=100r/m` — 100 requests/minute per IP.
- WebSocket: `/ws/*` proxied to notification service with `proxy_read_timeout 3600s`.

---

## 12. Frontend: React Dashboard

**Tech:** React 18 + TypeScript + Vite 5 + React Query + Recharts + Tailwind CSS + Zustand

### Component Map

```
src/pages/Dashboard.tsx
├── FHSGauge            ← Radial gauge 0-100, color-coded (red/amber/green)
├── SpendingPieChart    ← Recharts PieChart of category distribution
├── TrendLineChart      ← Recharts LineChart of monthly spending (from ClickHouse)
├── BudgetBar           ← Per-category progress bar (spent/limit)
├── TransactionTable    ← Recent 10 transactions with category badges
└── AlertBanner         ← Real-time alerts (WebSocket-driven)
```

### React Query API Hooks (`src/api/dashboard.ts`)

```typescript
import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';

export interface DashboardOverview {
  fhs: { score: number; computed_at: string; data_freshness: 'fresh' | 'stale' };
  categories: Array<{ category: string; amount: number; count: number }>;
  recent_transactions: Transaction[];
  unread_alerts: number;
  budget_status: Array<{ category: string; limit: number; spent: number; status: 'ok'|'warning'|'over' }>;
}

export function useDashboardOverview() {
  return useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: () => apiClient.get<DashboardOverview>('/api/v1/dashboard/overview'),
    staleTime: 30_000,     // matches Redis TTL — don't refetch within 30s
    refetchInterval: 60_000,
  });
}

export function useFHSHistory(months = 6) {
  return useQuery({
    queryKey: ['analytics', 'fhs', 'history', months],
    queryFn: () => apiClient.get(`/api/v1/analytics/fhs/history?months=${months}`),
  });
}
```

### Real-Time Alert WebSocket Hook (`src/hooks/useAlertWebSocket.ts`)

```typescript
import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../store/authStore';

export function useAlertWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const queryClient = useQueryClient();
  const token = useAuthStore(s => s.accessToken);

  useEffect(() => {
    if (!token) return;

    const ws = new WebSocket(`wss://${window.location.host}/ws/v1/alerts?token=${token}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const alert = JSON.parse(event.data);
      if (alert.type === 'alert') {
        // Invalidate dashboard cache so unread count refreshes
        queryClient.invalidateQueries({ queryKey: ['dashboard', 'overview'] });
        // Show toast notification
        showAlertToast(alert);
      }
    };

    // Keepalive ping every 30s
    const pingInterval = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send('ping'), 30_000);

    return () => { clearInterval(pingInterval); ws.close(); };
  }, [token]);
}
```

---

## 13. Design Patterns — Where, How, and Why

This section consolidates all five patterns with precise file locations and the software engineering reason each is used.

### Pattern 1: Adapter Pattern
| Aspect | Detail |
|---|---|
| **Where** | `services/ingestion/adapters/` |
| **What** | `ITransactionAdapter` (base.py) → `CSVUploadAdapter`, `ICICIBankAdapter`, `ManualEntryAdapter` |
| **How** | Each adapter implements `validate()` and `transform()`. `AdapterRegistry` maps `source_type` string to adapter instance. `IngestionService` calls `registry.get(source_type).transform(raw)` without knowing the source format. |
| **Why** | NFR-06: New bank integration in < 2 developer-days. Adding HDFC Bank requires writing one class and one registration line. Zero changes to `IngestionService` or any other code. |
| **GoF Classification** | Structural — converts incompatible interfaces to a target interface. |

### Pattern 2: Observer Pattern
| Aspect | Detail |
|---|---|
| **Where** | `services/ingestion/publishers/` (Subject side) + `services/anomaly/routers/internal_router.py` (Observer side) |
| **What** | `INotificationPublisher` ABC → `RestWebhookPublisher` (prototype) / `KafkaPublisher` (production stub) |
| **How** | After ingestion and analytics computation, the publisher calls each registered observer URL via HTTP POST. The Anomaly Detector's `/internal/events/analytics-complete` endpoint IS the `update()` method of the Observer interface. |
| **Why** | Decouples Analytics Engine from Anomaly Detector. Adding a new downstream consumer (e.g., a tax service) requires registering its URL in `NOTIFICATION_OBSERVERS` — zero code changes. Also enables clean Kafka migration. |
| **GoF Classification** | Behavioral — defines a one-to-many dependency so that when one object changes state, all its dependents are notified. |

### Pattern 3: Strategy Pattern (Categorization)
| Aspect | Detail |
|---|---|
| **Where** | `services/analytics/categorization/` |
| **What** | `ICategorizer` ABC → `RuleBasedCategorizer` (always active) + `LLMCategorizer` (feature-flagged) |
| **How** | `CategorizationService.categorize()` always calls `RuleBasedCategorizer` first. If `ENABLE_LLM_CATEGORIZATION=true` AND confidence < threshold, it calls `LLMCategorizer`. Results are interchangeable (both return `CategoryResult`). |
| **Why** | Enables runtime selection of algorithm without changing orchestration logic. The LLM can be turned on/off without code deployment — just change an env var. New classifiers (e.g., local BERT model) can be added by implementing `ICategorizer`. |
| **GoF Classification** | Behavioral — defines a family of algorithms, encapsulates each one, and makes them interchangeable. |

### Pattern 4: Factory Method (Analytics Processors)
| Aspect | Detail |
|---|---|
| **Where** | `services/analytics/factory.py` |
| **What** | `AnalyticsServiceFactory.create(processor_type)` → `FHSProcessor`, `CategoryAggregator`, `TrendAnalyzer` |
| **How** | The factory maps string keys to processor classes. The `AnalyticsService` orchestrator calls `factory.create("fhs")` without importing `FHSProcessor` directly. |
| **Why** | Decouples the orchestrator from concrete processor types. New analytics modules (e.g., `InvestmentAnalyzer`) are added by registering in the factory — the orchestrator loop does not change. |
| **GoF Classification** | Creational — defines an interface for creating an object but lets subclasses decide which class to instantiate. |

### Pattern 5: Facade Pattern (Dashboard API)
| Aspect | Detail |
|---|---|
| **Where** | `services/analytics/routers/analytics_router.py` — `GET /api/v1/dashboard/overview` endpoint |
| **What** | Single endpoint that aggregates: Redis FHS cache, ClickHouse category distribution, PostgreSQL recent transactions, PostgreSQL unread alert count |
| **How** | The endpoint runs all four data fetches (Redis first, then DB if cache miss), assembles a `DashboardOverview` response object, and returns it. The frontend calls one endpoint instead of four. |
| **Why** | Simplifies the frontend API surface. The frontend has zero knowledge of the underlying microservices architecture. Backend data sources can change (e.g., migrate from PostgreSQL to ClickHouse for aggregates) without frontend changes. |
| **GoF Classification** | Structural — provides a simplified interface to a complex subsystem. |

---

## 14. End-to-End Request Flows

### Flow 1: CSV Transaction Ingestion (Happy Path)

```
1. User uploads CSV via React Dashboard
   POST /api/v1/transactions/ingest (multipart/form-data, JWT in header)

2. nginx receives request
   → auth_request to phoenix-auth:8001/internal/validate-token
   → Auth service validates JWT, returns 200 + X-User-ID header
   → nginx injects X-User-ID into upstream request
   → nginx routes to phoenix-ingestion:8002

3. Ingestion Service (phoenix-ingestion:8002)
   → FastAPI receives request with user_id from X-User-ID header
   → AdapterRegistry.get("csv_v1") → CSVUploadAdapter
   → CSVUploadAdapter.validate(csv_content) → ValidationResult(is_valid=True)
   → CSVUploadAdapter.transform(csv_content) → [UnifiedTransaction x N]
   → For each UnifiedTransaction: INSERT into PostgreSQL transactions table
   → INSERT into audit_log (TRANSACTION_INGESTED)
   → RestWebhookPublisher.publish({event: "transactions_ingested", user_id, transaction_ids})
     → POST phoenix-analytics:8003/internal/trigger (Observer notification)
     → POST phoenix-anomaly:8004/internal/cache-invalidate (optional second observer)
   → Return {ingested: N, skipped: 0} to nginx → to frontend

4. Analytics Engine (phoenix-analytics:8003) [triggered synchronously]
   → POST /internal/trigger received
   → Load transactions from PostgreSQL
   → For each transaction:
     → CategorizationService.categorize(description, mcc_code, merchant_name)
       → RuleBasedCategorizer runs (always)
       → If ENABLE_LLM_CATEGORIZATION=true AND confidence < 0.7: LLMCategorizer runs
     → INSERT into transaction_categories
   → FHSProcessor.compute(user_id, metrics) → new FHS score
   → INSERT into financial_health_scores (PostgreSQL, append-only)
   → CacheInvalidator.invalidate_user(user_id) → Redis DEL fhs:{user_id}, dashboard:{user_id}:overview
   → ClickHouseWriter.write_fhs(user_id, fhs_data) [async, fire-and-forget]
   → RestWebhookPublisher.publish({event: "analytics-complete", user_id, transaction_ids})
     → POST phoenix-anomaly:8004/internal/events/analytics-complete

5. Anomaly Detection Service (phoenix-anomaly:8004) [Observer webhook]
   → POST /internal/events/analytics-complete received
   → For each transaction with category:
     → WelfordStateStore.get(user_id, category_id) from Redis
     → If None: rebuild from last 30 days of PostgreSQL transactions
     → ZScoreDetector.compute_z_score(amount, state)
     → WelfordState.update(amount) → new state
     → WelfordStateStore.save(user_id, category_id, new_state) to Redis
     → If |Z| > 2.5:
       → INSERT into anomaly_alerts (PostgreSQL)
       → POST phoenix-notification:8006/internal/push-alert

6. Notification Service (phoenix-notification:8006)
   → Alert received
   → ConnectionManager.push_alert(user_id, alert_payload)
   → WebSocket message delivered to React frontend (if connected)

7. React Frontend
   → useAlertWebSocket hook receives WebSocket message
   → queryClient.invalidateQueries(['dashboard', 'overview'])
   → React Query refetches dashboard (next request hits Redis, is < 50ms)
   → AlertBanner renders new alert
```

### Flow 2: Dashboard Load (Cache Hit)

```
1. GET /api/v1/dashboard/overview (JWT in header)
2. nginx auth_request → JWT valid → proxy to phoenix-analytics:8003
3. Analytics Engine checks Redis: GET dashboard:{user_id}:overview → HIT
4. Return cached JSON (< 5ms Redis read + ~10ms network)
5. Total latency: ~15–30ms ✓ (well within 300ms NFR-01)
```

### Flow 3: Dashboard Load (Cache Miss — first load after Redis restart)

```
1. GET /api/v1/dashboard/overview
2. Analytics Engine: Redis MISS on dashboard:{user_id}:overview
3. Parallel fetches:
   a. Redis GET fhs:{user_id} → MISS → PostgreSQL: SELECT last FHS score
   b. ClickHouse: SELECT category, SUM(amount) for current month
   c. PostgreSQL: SELECT last 5 transactions
   d. PostgreSQL: SELECT COUNT(*) unread alerts
4. Assemble DashboardOverview object
5. Redis SET dashboard:{user_id}:overview (TTL: 30s)
6. Return response (~200–400ms on cold cache)
```

---

## 15. Testing Strategy

### Unit Tests (per service, `tests/unit/`)

Each service's core logic is tested in isolation using `pytest` with mocked dependencies.

```python
# tests/unit/test_z_score_detector.py
import pytest
from services.anomaly.detector import ZScoreDetector, WelfordState

def test_z_score_suppressed_below_min_transactions():
    detector = ZScoreDetector()
    state = WelfordState(count=5, mean=100.0, M2=200.0)  # only 5 transactions
    assert detector.compute_z_score(500.0, state) is None  # suppressed

def test_z_score_anomaly_detected():
    detector = ZScoreDetector()
    # 10 transactions with mean 100, std_dev ~10
    state = WelfordState(count=15, mean=100.0, M2=1500.0)
    z = detector.compute_z_score(500.0, state)
    assert z is not None
    assert abs(z) > detector.THRESHOLD

def test_welford_update_incrementally():
    state = WelfordState(count=0, mean=0.0, M2=0.0)
    for value in [100, 100, 100, 100, 100]:
        state = state.update(value)
    assert state.mean == 100.0
    assert state.std_dev == 0.0

# tests/unit/test_categorization_strategy.py
import pytest
from unittest.mock import AsyncMock, patch
from services.analytics.categorization.service import CategorizationService
from services.analytics.categorization.base import CategorizationMethod

@pytest.mark.asyncio
async def test_rule_based_used_when_llm_disabled():
    service = CategorizationService(redis_client=None)
    service.llm_enabled = False
    result = await service.categorize("SWIGGY ORDER 12345", None, "Swiggy")
    assert result.method in [CategorizationMethod.RULE_MERCHANT, CategorizationMethod.RULE_KEYWORD]

@pytest.mark.asyncio
async def test_llm_fallback_on_llm_failure():
    """When LLM fails, rule-based result must be returned."""
    service = CategorizationService(redis_client=AsyncMock())
    service.llm_enabled = True
    service.llm_threshold = 1.0  # Force LLM for all transactions
    service.llm_categorizer = AsyncMock()
    service.llm_categorizer.categorize.side_effect = Exception("OpenAI API unavailable")
    result = await service.categorize("AMAZON PURCHASE", None, None)
    assert result is not None  # Should return rule-based result, not raise
```

### Integration Tests (`tests/integration/`)

Integration tests spin up Docker Compose and run real HTTP requests through the full stack.

```python
# tests/integration/test_ingestion_pipeline.py
import httpx, pytest

BASE = "http://localhost:80"

@pytest.fixture(scope="module")
def auth_token():
    r = httpx.post(f"{BASE}/api/v1/auth/login",
                   json={"email": "test@phoenix.dev", "password": "TestPass123!"})
    assert r.status_code == 200
    return r.json()["access_token"]

def test_end_to_end_csv_ingestion(auth_token):
    csv_data = "date,amount,description\n2026-04-10,1500.00,SWIGGY ORDER\n2026-04-11,200.00,METRO RAIL"
    headers = {"Authorization": f"Bearer {auth_token}"}
    r = httpx.post(f"{BASE}/api/v1/transactions/ingest",
                   files={"file": ("test.csv", csv_data, "text/csv")},
                   data={"source_type": "csv_v1"},
                   headers=headers)
    assert r.status_code == 200
    assert r.json()["ingested"] == 2

def test_dashboard_after_ingestion(auth_token):
    import time; time.sleep(2)  # Allow analytics pipeline to complete
    r = httpx.get(f"{BASE}/api/v1/dashboard/overview",
                  headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    data = r.json()
    assert "fhs" in data
    assert data["fhs"]["score"] >= 0
    assert len(data["categories"]) > 0
```

### Audit Log Immutability Test

```python
def test_audit_log_immutable(db_session):
    """Critical compliance test: audit_log must reject UPDATE and DELETE."""
    import sqlalchemy, pytest
    with pytest.raises(sqlalchemy.exc.InternalError, match="immutable"):
        db_session.execute("UPDATE audit_log SET operation = 'TAMPERED' WHERE id IS NOT NULL")
```

---

## 16. Performance Benchmarking (Locust)

**`tests/load/locustfile.py`**

```python
from locust import HttpUser, task, between, events
import json, random

class PhoenixUser(HttpUser):
    wait_time = between(1, 3)
    token: str = None

    def on_start(self):
        """Login once per virtual user."""
        r = self.client.post("/api/v1/auth/login",
                             json={"email": f"loadtest{random.randint(1,100)}@test.com",
                                   "password": "LoadTest123!"})
        self.token = r.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(10)
    def get_dashboard_overview(self):
        """Most frequent operation — tests cache-aside performance."""
        self.client.get("/api/v1/dashboard/overview", headers=self.headers,
                        name="GET /dashboard/overview")

    @task(3)
    def get_fhs_history(self):
        self.client.get("/api/v1/analytics/fhs/history?months=6", headers=self.headers,
                        name="GET /analytics/fhs/history")

    @task(2)
    def get_transactions(self):
        self.client.get("/api/v1/transactions?page=1&page_size=20", headers=self.headers,
                        name="GET /transactions")

    @task(1)
    def get_recommendations(self):
        self.client.get("/api/v1/recommendations/budget", headers=self.headers,
                        name="GET /recommendations/budget")
```

**Run benchmark:**
```bash
# From project root
locust -f tests/load/locustfile.py --headless \
  -u 500 -r 50 \          # 500 users, spawn 50/second
  --run-time 120s \        # Run for 2 minutes
  --html docs/benchmarks/report_500u.html \
  --host https://localhost
```

**Collect fault tolerance metric:**
```bash
# In one terminal: run Locust at 200 users
locust -f tests/load/locustfile.py --headless -u 200 -r 20 --run-time 90s

# In another terminal: kill analytics engine at t=30s
docker compose stop phoenix-analytics
sleep 30
docker compose start phoenix-analytics

# Expected: 0% error rate during outage (dashboard serves stale cache)
# Expected: auto-recovery in < 30s
```

---

## 17. Environment Variables Reference

Create `infra/.env` (never commit to git):

```bash
# PostgreSQL
POSTGRES_PASSWORD=supersecretpassword

# Redis
REDIS_PASSWORD=redissecretpassword

# JWT (generate with: openssl genrsa -out private.pem 2048 && openssl rsa -in private.pem -pubout -out public.pem)
JWT_PRIVATE_KEY=<base64-encoded PEM private key>
JWT_PUBLIC_KEY=<base64-encoded PEM public key>

# Categorization — set to 'true' to enable LLM enhancement layer
ENABLE_LLM_CATEGORIZATION=false
OPENAI_API_KEY=sk-...    # Only needed if ENABLE_LLM_CATEGORIZATION=true
LLM_CONFIDENCE_THRESHOLD=0.7

# Anomaly Detection
ANOMALY_Z_THRESHOLD=2.5
ANOMALY_MIN_TRANSACTIONS=10

# Observer notification (REST webhook targets)
NOTIFICATION_BACKEND=rest
# NOTIFICATION_BACKEND=kafka    # TODO:KAFKA — set this to enable Kafka mode

# Kafka (only used when NOTIFICATION_BACKEND=kafka — future)
# KAFKA_BOOTSTRAP_SERVERS=kafka:9092
```

---

## 18. Running the Project Locally

### Prerequisites

- Docker Desktop 4.x (or Docker Engine 25 + Compose v2)
- 8 GB RAM minimum allocated to Docker
- `openssl` (for generating TLS cert and JWT keys)

### Step 1: Clone and Initialize

```bash
git clone https://github.com/team23/phoenix.git
cd phoenix

# Generate self-signed TLS certificate (prototype only)
mkdir -p services/gateway/certs
openssl req -x509 -newkey rsa:4096 -keyout services/gateway/certs/server.key \
  -out services/gateway/certs/server.crt -days 365 -nodes \
  -subj "/CN=localhost/O=Phoenix/C=IN"

# Generate RS256 JWT key pair
openssl genrsa -out /tmp/jwt_private.pem 2048
openssl rsa -in /tmp/jwt_private.pem -pubout -out /tmp/jwt_public.pem

# Create .env
cd infra
cp .env.example .env
echo "JWT_PRIVATE_KEY=$(base64 -w0 /tmp/jwt_private.pem)" >> .env
echo "JWT_PUBLIC_KEY=$(base64 -w0 /tmp/jwt_public.pem)" >> .env
```

### Step 2: Start Infrastructure

```bash
cd infra

# Start infrastructure services first
docker compose up -d postgres redis clickhouse

# Wait for health checks
docker compose ps   # All three should show "healthy"
```

### Step 3: Start Application Services

```bash
# Build and start all services
docker compose up -d --build

# Watch logs
docker compose logs -f phoenix-analytics phoenix-ingestion phoenix-anomaly
```

### Step 4: Verify

```bash
# Health checks (all should return {"status": "ok"})
curl -k https://localhost/api/v1/auth/health/ready
curl -k https://localhost/api/v1/analytics/health/ready

# Register a test user
curl -k -X POST https://localhost/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@phoenix.dev", "display_name": "Test User", "password": "TestPass123!"}'

# Login
TOKEN=$(curl -k -s -X POST https://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@phoenix.dev", "password": "TestPass123!"}' | jq -r .access_token)

# Ingest sample CSV
curl -k -X POST https://localhost/api/v1/transactions/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@infra/postgres/sample_transactions.csv" \
  -F "source_type=csv_v1"

# Check dashboard
curl -k -H "Authorization: Bearer $TOKEN" https://localhost/api/v1/dashboard/overview | jq .
```

### Step 5: Access the Dashboard

Navigate to `https://localhost` in your browser (accept the self-signed certificate warning).

### Step 6: Enable LLM Categorization (Optional)

```bash
# Edit infra/.env
ENABLE_LLM_CATEGORIZATION=true
OPENAI_API_KEY=sk-your-key-here

# Restart only the analytics service (no other service restart needed)
docker compose restart phoenix-analytics

# Verify LLM is active
docker compose logs phoenix-analytics | grep "LLM categorization: ENABLED"
```

### Common Troubleshooting

| Issue | Fix |
|---|---|
| ClickHouse not starting | Increase Docker memory to 8 GB in Docker Desktop settings |
| Redis auth failure | Verify `REDIS_PASSWORD` in `.env` matches the value in `docker-compose.yml` |
| JWT validation 401 errors | Ensure `JWT_PUBLIC_KEY` env var in auth service matches the key pair used to sign tokens |
| LLM categorization not working | Check `OPENAI_API_KEY` is set and `ENABLE_LLM_CATEGORIZATION=true` |
| Dashboard showing stale data | Run `docker compose restart phoenix-analytics` to trigger a fresh cache write |
| Anomaly detection not triggering | Need at least 10 transactions in a category — load the seed data: `docker compose exec postgres psql -U phoenix -f /docker-entrypoint-initdb.d/02-seed.sql` |

---

*End of IMPLEMENTATION.md — Phoenix, Team 23, S26CS6.401*
