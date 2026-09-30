# Phoenix - Intelligent Personal Financial Analytics Platform

A microservices-based personal finance analytics platform that transforms raw transaction data into actionable financial insights through intelligent categorization, anomaly detection, and personalized recommendations.

> Built as the Course-Project for **S26CS6.401 Software Engineering**.


## Architecture

```
┌──────────┐     ┌──────────────┐     ┌────────────────┐
│  React   │────▶│  nginx GW    │────▶│  Auth Service  │
│ Frontend │     │ (TLS + JWT)  │     │  (RS256 JWT)   │
└──────────┘     └──────┬───────┘     └────────────────┘
                        │
           ┌────────────┼────────────┐
           ▼            ▼            ▼
    ┌─────────────┐ ┌──────────┐ ┌───────────────┐
    │ Ingestion   │ │Analytics │ │ Anomaly       │
    │ (Adapter)   │─│(Strategy)│─│ (Welford Z)   │
    └─────────────┘ └──────────┘ └───────────────┘
           │            │                │
    ┌──────┴──────┐     │         ┌──────┴──────┐
    │Recommendation│    │         │Notification │
    │ (Strategy)  │     │         │ (WebSocket) │
    └─────────────┘     │         └─────────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────────┐
    │PostgreSQL│  │  Redis   │  │  ClickHouse  │
    │  (OLTP)  │  │ (Cache)  │  │ (Analytics)  │
    └──────────┘  └──────────┘  └──────────────┘
```

## Design Patterns

| Pattern | Location | Purpose |
|---------|----------|---------|
| **Adapter** | `services/ingestion/adapters/` | Normalize diverse bank/CSV/manual data into `UnifiedTransaction` |
| **Observer** | `services/ingestion/publishers/` | Notify Analytics/Anomaly services after ingestion |
| **Strategy** | `services/analytics/categorization/` | Switch between rule-based and LLM categorization |
| **Strategy** | `services/recommendation/strategies/` | Switch between 50/30/20 and statistical budget recommendations |
| **Factory Method** | `services/analytics/factory.py` | Create analytics processors without knowing concrete types |
| **Facade** | `services/analytics/service.py` | Unified dashboard overview aggregating multiple data sources |

## Services

| Service | Port | Description |
|---------|------|-------------|
| Auth | 8001 | JWT RS256 token issuance, user registration/login, RBAC |
| Ingestion | 8002 | CSV upload, manual entry, bank API ingestion with deduplication |
| Analytics | 8003 | Transaction categorization, FHS computation, spending trends |
| Anomaly | 8004 | Z-score anomaly detection with Welford's online algorithm |
| Recommendation | 8005 | Personalized budget recommendations (50/30/20 + statistical) |
| Notification | 8006 | Real-time WebSocket alerts |
| Gateway | 443 | nginx reverse proxy with TLS, JWT validation, rate limiting |
| Frontend | 3000 | React SPA with dashboard, transactions, and recommendations |

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy (async), Pydantic
- **Frontend**: React 18, TypeScript, Vite, Recharts, Zustand, React Query
- **Databases**: PostgreSQL 15 (OLTP), ClickHouse (analytics), Redis (cache/Welford state)
- **Infrastructure**: Docker, nginx, Locust (load testing)
- **Security**: JWT RS256, bcrypt password hashing, Row-Level Security (RLS)

## Polyglot Persistence: Why ClickHouse?

Phoenix uses a **dual-database strategy** to balance transactional consistency with analytical performance:

### The Problem

Transactional databases (PostgreSQL) excel at ACID writes but struggle with analytical queries:
- **FHS history**: `SELECT * FROM financial_health_scores ORDER BY computed_at DESC LIMIT 12` takes ~850ms for 50k transactions
- **Spending trends**: `SELECT toStartOfMonth(ts), SUM(amount) FROM transactions GROUP BY toStartOfMonth(ts)` takes ~1,200ms
- **Category trends**: Multiple JOINs, full table scans, no compression

These latencies violate the non-functional performance requirement (analytics queries < 1s).

### The Solution: Columnar OLAP (ClickHouse)

ClickHouse is optimized for **analytical** (OLAP) workloads through:

1. **Columnar Storage**
   - PostgreSQL (row-based): full rows deserialized for every query
   - ClickHouse: only requested columns read from disk; minimal I/O
   - For `SUM(amount)`, ClickHouse reads the `amount` column (contiguous bytes) not entire transaction records

2. **Partitioning by Time**
   - Monthly partitions enable **partition pruning**: range queries skip entire months
   - "Last 6 months of spending" doesn't even look at 2024 data

3. **Compression**
   - Columnar data exhibits high redundancy: 100 transactions in same category, same currency
   - ClickHouse achieves **5–20x compression** → fewer disk I/Os, better CPU cache utilization

4. **Simplified Queries**
   - Pre-aggregated tables (`monthly_category_spending`) eliminate GROUP BY operations
   - No JOINs: data denormalized for analytical access patterns

### Benchmark Results

Running `benchmarks/clickhouse_benchmark.py` on 50,000 synthetic transactions:

| Query | PostgreSQL | ClickHouse | Speed-up |
|-------|-----------|-----------|----------|
| FHS history (12 months) | 850ms | 45ms | **18.9x** ⚡ |
| Monthly spending aggregate | 1,200ms | 65ms | **18.5x** ⚡ |
| Category distribution | 950ms | 52ms | **18.3x** ⚡ |

**Result**: All analytical queries now complete well under 1 second ✓ (NFR-01 achieved)

### Architecture: Eventual Consistency

```
PostgreSQL (OLTP — source of truth)
    ↓ [async fire-and-forget mirror]
ClickHouse (OLAP — ~1-2s lag)
    ↓ [ClickHouse-first read with PG fallback]
API responses include "data_source" field
```

- **Writes**: PostgreSQL immediately (ACID)
- **Analytics writes**: Asynchronously mirrored to ClickHouse by the Analytics Engine
- **Reads**: ClickHouse first (fast); PostgreSQL fallback if CH unavailable
- **Eventual consistency**: Acceptable for trend analysis (1-2s lag is imperceptible to users)

### Non-Functional Requirements Met

| Requirement | Solution |
|-------------|----------|
| **Performance**: Analytics queries < 1s | ClickHouse columnar + partitioning: 18–20x speedup |
| **Scalability**: Support 100k+ transactions/user | Monthly partitions + pre-aggregation + compression |
| **Availability**: Analytical queries available even if ClickHouse down | PostgreSQL fallback in dual-read pattern |
| **Data consistency**: Within acceptable bounds for analytics | 1–2s async replication; FHS recomputed per ingestion |

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 20+ (for frontend development)

### Setup
```bash
# 1. Clone and configure
git clone https://github.com/amrithav27/intelligent-personal-financial-analytics-platform.git
cd intelligent-personal-financial-analytics-platform/infra
cp .env.example .env
# Edit .env and replace the placeholder POSTGRES_PASSWORD / REDIS_PASSWORD values.

# 2. Generate RSA keys for JWT and write them directly into .env
openssl genrsa -out jwt_private.pem 2048
openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem

sed -i "s|^JWT_PRIVATE_KEY=.*|JWT_PRIVATE_KEY=$(base64 -w0 jwt_private.pem)|" .env
sed -i "s|^JWT_PUBLIC_KEY=.*|JWT_PUBLIC_KEY=$(base64 -w0 jwt_public.pem)|" .env

rm jwt_private.pem jwt_public.pem

# 3. Generate the self-signed TLS certificate for the nginx gateway
#    (not committed -- see services/gateway/certs/README.md)
openssl req -x509 -newkey rsa:4096 -nodes -days 365 \
  -keyout ../services/gateway/certs/server.key \
  -out ../services/gateway/certs/server.crt \
  -subj "/CN=localhost"

# 4. Start all services
sudo docker compose up --build -d

# 5. Access the platform (accept the self-signed certificate warning)
#    Frontend: https://localhost
#    API docs: https://localhost/api/v1/auth/docs

# 6. Stop docker containers safely
sudo docker compose down
```

`sample_transactions.csv` in the repo root is a ready-made file for exercising the CSV
upload path.

### Development

```bash
# Frontend development
cd frontend
npm install
npm run dev  # Runs on http://localhost:3000

# Run unit tests
cd ..
python -m pytest tests/unit/ -v

# Run load tests
locust -f tests/load/locustfile.py --host=https://localhost
```

## Transaction Categorization

Three-tier rule-based categorization with optional LLM upgrade:

1. **MCC Code** (confidence: 0.95) — ~250 ISO 18245 codes mapped
2. **Merchant Name** (confidence: 0.90) — ~150 Indian merchants mapped
3. **Keyword/Regex** (confidence: 0.70) — 28 regex patterns

When `ENABLE_LLM_CATEGORIZATION=true` and rule-based confidence < 0.7, the system uses GPT-4o-mini with Redis caching (24h TTL).

## Financial Health Score (FHS)

0–100 composite metric from four equally-weighted (25 pts each) components:

| Component | Weight | Calculation |
|-----------|--------|-------------|
| Savings Rate | 25 pts | `min(savings_rate / 0.20, 1.0)` |
| Debt-to-Income | 25 pts | `max(0, 1 - DTI / 0.36)` |
| Spending Volatility | 25 pts | `max(0, 1 - CV / 0.50)` |
| Emergency Fund | 25 pts | `min(months / 3, 1.0)` |

## Anomaly Detection

Uses **Welford's Online Algorithm** for O(1) incremental running mean and standard deviation per user per category:

- **Z-score threshold**: 2.5 (configurable via `ANOMALY_Z_THRESHOLD`)
- **Bootstrap suppression**: No alerts until ≥10 transactions per category
- **Real-time delivery**: WebSocket push to connected clients

## Project Structure

```
├── infra/                    # Infrastructure configs
│   ├── docker-compose.yml    # All services orchestration
│   ├── postgres/init.sql     # Full schema & triggers
│   ├── postgres/seed.sql     # 50 transactions dev data
│   ├── clickhouse/init.sql   # Analytical tables
│   └── .env.example          # Environment template
├── services/
│   ├── auth/                 # JWT authentication
│   ├── ingestion/            # Transaction ingestion (Adapter pattern)
│   │   ├── adapters/         # CSV, ICICI, Manual adapters
│   │   └── publishers/       # REST webhook, Kafka stub
│   ├── analytics/            # Analytics engine
│   │   ├── categorization/   # Strategy pattern (Rule + LLM)
│   │   │   └── rules/        # MCC codes, merchants, keywords
│   │   └── processors/       # FHS, category aggregator, trends
│   ├── anomaly/              # Z-score anomaly detection
│   ├── recommendation/       # Budget recommendations
│   │   └── strategies/       # 50/30/20 + statistical
│   ├── notification/         # WebSocket alerts
│   └── gateway/              # nginx reverse proxy (TLS certs generated at setup)
├── frontend/                 # React SPA
│   └── src/
│       ├── api/              # API hooks (React Query)
│       ├── pages/            # Dashboard, Transactions, etc.
│       └── store/            # Zustand auth state
├── tests/
│   ├── unit/                 # pytest unit tests
│   ├── integration/          # cross-service tests
│   └── load/                 # Locust load tests + raw NFR results
├── benchmarks/               # ClickHouse vs PostgreSQL benchmark + results
├── ALTERNATE_ARCH/           # Monolithic implementation for architecture comparison
├── docs/
│   ├── diagrams/             # PlantUML sources + rendered PNGs
│   └── screenshots/          # UI screenshots
├── IMPLEMENTATION.md         # Detailed implementation guide
└── Report.pdf                # Technical report
```

## Security

- **JWT RS256**: Asymmetric key signing (private key for Auth Service only, public key for all services)
- **bcrypt**: Password hashing with 12 rounds
- **Row-Level Security**: PostgreSQL RLS policies ensure users can only access their own data
- **Audit Log**: Immutable `audit_log` table with SHA-256 payload hashes
- **TLS**: nginx handles HTTPS termination
- **Rate Limiting**: 100 req/min per IP with burst allowance

## Codebase Implementation Summary

The Phoenix platform is implemented as a suite of decoupled, single-responsibility microservices built with **FastAPI** and **asyncio**, utilizing a polyglot persistence architecture backing onto **PostgreSQL** (OLTP), **Redis** (Caching/State), and **ClickHouse** (OLAP). 
- **Ingestion & Integration**: Uses the **Adapter Pattern** to ingest normalized streams from synthetic bank APIs, CSV uploads, and manual entry, pushing to the analytics pipe via REST. 
- **Compute Layer**: Financial Health Score (FHS) and complex multi-source categorization execute inside the Analytics service using the **Strategy Pattern** (toggling seamlessly between heuristic-based dictionary matches and LLM-based categorization pipelines).
- **Event-Driven Resilience**: Adopts an **Observer Pattern** architecture where Welford's algorithm continuously computes moving standard deviations of transaction streams for Z-score anomaly detection, ultimately pumping to a persistent WebSocket Notification service proxy.
- **Architectural Tactics applied**: Significant thread-pool offloading for cryptographic bottlenecks (bcrypt auth loops), widespread SQLAlchemy concurrent connection pooling, and two-tier Nginx proxy caching (including `stale-while-revalidate` proxy bypasses) ensure rigid high-concurrency uptime.

## NFR Benchmark Results

The platform has been rigorously load-tested against its Quantified Non-Functional Requirements using **Locust**, simulating heavy concurrency, massive transaction ingestion scenarios, and chaotic container failures to validate architectural resiliency. 

| NFR | Metric | Target | Actual Evaluated Value | Status |
|-----|--------|--------|------------------------|--------|
| **NFR-01 Performance** | p95 latency `GET /dashboard/overview` (cache hit) | < 50ms | **34 ms** |  PASSED |
| **NFR-01 Performance** | p95 latency `GET /dashboard/overview` (cache miss) | < 600ms | **532 ms** |  PASSED |
| **NFR-02 Scalability** | Sustained asynchronous throughput limit | > 290 RPS | **625.58 RPS** |  PASSED |
| **NFR-04 Fault Tolerance** | Dashboard availability during Analytics Engine crash | 100% | **100% (served via proxy stale cache)** |  PASSED |
| **NFR-04 Recovery** | Real-world MTTR after primary backend container crash | < 30 seconds | **2.02 seconds** |  PASSED |

*Load tests were conducted via Locust scaling to 500 concurrent virtual users.*

## Architecture Comparison

`ALTERNATE_ARCH/` holds a monolithic implementation of the same functionality, benchmarked
against the microservices build under identical Locust scenarios. See
[`ALTERNATE_ARCH/ARCHITECTURE_COMPARISON.md`](ALTERNATE_ARCH/ARCHITECTURE_COMPARISON.md) for
the trade-off discussion and `ALTERNATE_ARCH/Monolith_NFR0*.csv` for its raw results.

## Documentation

| Document | Contents |
|----------|----------|
| [`IMPLEMENTATION.md`](IMPLEMENTATION.md) | Service-by-service implementation guide: schemas, endpoints, pattern walkthroughs |
| [`Report.pdf`](Report.pdf) | Technical report — requirements, IEEE 42010 views, ADRs, tactics, analysis |
| [`docs/diagrams/`](docs/diagrams/) | C4, deployment, ERD, sequence and per-pattern diagrams (PlantUML sources + PNGs) |
| [`docs/screenshots/`](docs/screenshots/) | UI screenshots of the running platform |
| [`benchmarks/README.md`](benchmarks/README.md) | ClickHouse vs PostgreSQL benchmark methodology |
| [`tests/load/nfr_results.md`](tests/load/nfr_results.md) | Raw NFR load-test output |

## Contributors

Team 23, S26CS6.401 Software Engineering, IIIT Hyderabad. Amritha Vinod, Ananya Halgatti, Janya Gupta, Kriti Gupta,Priyanshi Gupta 
