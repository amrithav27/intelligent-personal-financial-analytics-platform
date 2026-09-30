# ClickHouse vs PostgreSQL Benchmark

Standalone benchmark script that proves ClickHouse's OLAP advantages over PostgreSQL, as per **ADR-002** (Polyglot Persistence Architecture).

## What It Does

1. Inserts 50K synthetic financial transactions into both databases
2. Runs 5 identical analytical queries against both
3. Measures **latency**, **compression**, and **throughput**
4. Generates an HTML visual report + JSON log

## Prerequisites

```bash
# Phoenix Docker stack must be running
cd infra && docker compose up -d

# Install minimal dependencies (NOT part of app requirements)
pip install psycopg2-binary requests
```

## Run

```bash
# Default: 50K rows, 5 iterations per query
python benchmarks/clickhouse_benchmark.py

# Custom configuration
BENCH_ROWS=100000 BENCH_ITERATIONS=10 python benchmarks/clickhouse_benchmark.py
```

## Output

- `benchmarks/results/benchmark_report.html` — Visual HTML report
- `benchmarks/results/benchmark_results.json` — Raw JSON metrics

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PG_HOST` | `localhost` | PostgreSQL host |
| `PG_PORT` | `5433` | PostgreSQL port |
| `PG_PASS` | `phoenix_secret_2024` | PostgreSQL password |
| `CH_URL` | `http://localhost:8123` | ClickHouse HTTP URL |
| `BENCH_ROWS` | `50000` | Rows to insert |
| `BENCH_ITERATIONS` | `5` | Query iterations per benchmark |

## What It Proves

- **Columnar storage**: ClickHouse reads only needed columns for aggregations
- **Compression**: LZ4/ZSTD per-column vs row-level TOAST
- **Partition pruning**: Time-range queries skip irrelevant partitions
- **Analytical query speed**: GROUP BY, SUM, AVG are ClickHouse's strength
