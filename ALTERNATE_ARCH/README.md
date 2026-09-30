# Alternate Architecture — Monolithic Layered

This directory contains a **minimal monolithic implementation** of the Phoenix platform, built for **NFR comparison** against the primary microservices architecture.

## Quick Start

```bash
# 1. Build and start the monolith (requires Docker)
sudo docker compose up -d --build

# 2. Wait for healthy status
curl http://localhost:9000/health/ready

# 3. Run benchmarks
pip install locust httpx
bash run_monolith_benchmarks.sh

# 4. Or run the unified benchmark directly
python benchmark.py --arch monolith --base-url http://localhost:9000
```

## Files

| File | Purpose |
|------|---------|
| `app.py` | Single FastAPI monolith — all domains inline |
| `models.py` | Unified SQLAlchemy models |
| `Dockerfile` | Single container image |
| `docker-compose.yml` | PostgreSQL + monolith (2 containers) |
| `benchmark.py` | Unified NFR benchmark script |
| `monolith_locustfile.py` | Locust load test scenarios |
| `run_monolith_benchmarks.sh` | Automated benchmark runner |
| `run_comparison.sh` | Full comparison (both architectures) |
| `ARCHITECTURE_COMPARISON.md` | Detailed analysis document |

## Architecture Differences

| Aspect | Microservices (current) | Monolith (this) |
|--------|:-----------------------:|:---------------:|
| Processes | 7 services + nginx | 1 app |
| Containers | 9+ | 2 |
| Databases | PostgreSQL + Redis + ClickHouse | PostgreSQL only |
| Caching | Redis (30s TTL) | None |
| Patterns | Strategy, Observer, Adapter, Factory | Direct function calls |
| Fault isolation | Per-service | None |
