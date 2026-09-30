#!/usr/bin/env python3
"""
Phoenix Platform — ClickHouse vs PostgreSQL Benchmark Demo
============================================================
Standalone script that proves ClickHouse's advantages for analytical (OLAP)
workloads as described in ADR-002.

This script:
  1. Connects to both PostgreSQL and ClickHouse (via Docker containers)
  2. Inserts synthetic financial transactions into both databases
  3. Runs identical analytical queries against both
  4. Measures latency, compression, and throughput
  5. Generates an HTML visual report + JSON log

Usage:
    pip install psycopg2-binary requests
    python benchmarks/clickhouse_benchmark.py

Prerequisites:
    - Phoenix Docker stack running (docker compose up -d in infra/)
    - PostgreSQL on localhost:5433
    - ClickHouse on localhost:8123
"""

import json
import os
import random
import statistics
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Third-party (minimal deps — no heavy analytics libs needed)
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2-binary is required. Install with: pip install psycopg2-binary")
    exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests is required. Install with: pip install requests")
    exit(1)


# ── Configuration ──────────────────────────────────────────────────────────
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5433"))
PG_DB = os.getenv("PG_DB", "phoenix")
PG_USER = os.getenv("PG_USER", "phoenix")
PG_PASS = os.getenv("PG_PASS", "supersecretpassword")

CH_URL = os.getenv("CH_URL", "http://localhost:8123")
CH_DB = os.getenv("CH_DB", "phoenix")

NUM_ROWS = int(os.getenv("BENCH_ROWS", "50000"))  # Rows to insert
QUERY_ITERATIONS = int(os.getenv("BENCH_ITERATIONS", "5"))  # Runs per query

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

CATEGORIES = [
    (1, "Groceries"), (2, "Transportation"), (3, "Utilities"),
    (4, "Entertainment"), (5, "Healthcare"), (6, "Dining"),
    (7, "Shopping"), (8, "Education"), (9, "Travel"),
    (10, "Investments"), (11, "Rent/Housing"), (12, "Insurance"),
    (13, "Personal Care"), (14, "Subscriptions"), (15, "Other"),
]

USER_IDS = [str(uuid.uuid4()) for _ in range(20)]  # 20 synthetic users


# ── Data Generation ────────────────────────────────────────────────────────

def generate_transactions(n: int) -> list[dict]:
    """Generate n synthetic financial transactions."""
    print(f"  Generating {n:,} synthetic transactions...")
    txns = []
    base_date = datetime(2025, 1, 1)
    for i in range(n):
        cat_id, cat_name = random.choice(CATEGORIES)
        user_id = random.choice(USER_IDS)
        amount = round(random.uniform(-50000, -10) if random.random() < 0.85 else random.uniform(10, 150000), 4)
        ts = base_date + timedelta(
            days=random.randint(0, 450),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        txns.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "amount": amount,
            "currency": random.choice(["INR", "INR", "INR", "USD", "EUR"]),
            "category_id": cat_id,
            "category_name": cat_name,
            "ts": ts,
        })
    return txns


# ── PostgreSQL Operations ──────────────────────────────────────────────────

def pg_connect():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS,
    )


def pg_setup_benchmark_table(conn):
    """Create a benchmark-specific table (NOT touching production data)."""
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS benchmark_transactions CASCADE;")
        cur.execute("""
            CREATE TABLE benchmark_transactions (
                id          UUID PRIMARY KEY,
                user_id     UUID NOT NULL,
                amount      NUMERIC(18,4) NOT NULL,
                currency    CHAR(3) NOT NULL DEFAULT 'INR',
                category_id INT NOT NULL,
                category_name TEXT NOT NULL,
                ts          TIMESTAMPTZ NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX idx_bench_user_ts ON benchmark_transactions(user_id, ts DESC);
        """)
    conn.commit()


def pg_insert(conn, txns: list[dict]) -> float:
    """Bulk insert transactions into PostgreSQL. Returns time in seconds."""
    start = time.perf_counter()
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO benchmark_transactions (id, user_id, amount, currency, category_id, category_name, ts)
               VALUES %s""",
            [(t["id"], t["user_id"], t["amount"], t["currency"],
              t["category_id"], t["category_name"], t["ts"]) for t in txns],
            page_size=1000,
        )
    conn.commit()
    return time.perf_counter() - start


def pg_query(conn, query: str) -> tuple[list, float]:
    """Execute query, return (rows, time_seconds)."""
    start = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    elapsed = time.perf_counter() - start
    return rows, elapsed


def pg_table_size(conn) -> int:
    """Get size of benchmark_transactions in bytes."""
    with conn.cursor() as cur:
        cur.execute("SELECT pg_total_relation_size('benchmark_transactions');")
        return cur.fetchone()[0]


def pg_cleanup(conn):
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS benchmark_transactions CASCADE;")
    conn.commit()


# ── ClickHouse Operations ──────────────────────────────────────────────────

def ch_query_raw(query: str, database: str = CH_DB) -> requests.Response:
    return requests.post(f"{CH_URL}/?database={database}", data=query, timeout=30)


def ch_setup_benchmark_table():
    """Create a benchmark-specific table in ClickHouse."""
    ch_query_raw("DROP TABLE IF EXISTS benchmark_transactions", CH_DB)
    ch_query_raw("""
        CREATE TABLE benchmark_transactions (
            id           UUID,
            user_id      UUID,
            amount       Decimal(18,4),
            currency     FixedString(3),
            category_id  Int32,
            category_name String,
            ts           DateTime,
            created_at   DateTime DEFAULT now()
        ) ENGINE = MergeTree()
          PARTITION BY toYYYYMM(ts)
          ORDER BY (user_id, ts)
    """, CH_DB)


def ch_insert(txns: list[dict]) -> float:
    """Bulk insert transactions into ClickHouse using TSV format. Returns time in seconds."""
    # Build TSV rows
    rows = []
    for t in txns:
        ts_str = t["ts"].strftime("%Y-%m-%d %H:%M:%S")
        rows.append(f"{t['id']}\t{t['user_id']}\t{t['amount']}\t{t['currency']}\t"
                    f"{t['category_id']}\t{t['category_name']}\t{ts_str}\t{ts_str}")
    tsv_data = "\n".join(rows)
    query = ("INSERT INTO benchmark_transactions "
             "(id, user_id, amount, currency, category_id, category_name, ts, created_at) "
             "FORMAT TSV")
    start = time.perf_counter()
    resp = requests.post(f"{CH_URL}/?database={CH_DB}&query={query}", data=tsv_data, timeout=60)
    resp.raise_for_status()
    elapsed = time.perf_counter() - start
    return elapsed


def ch_query(query: str) -> tuple[list, float]:
    """Execute query through ClickHouse HTTP, return (rows, time_seconds)."""
    full_query = f"{query} FORMAT JSON"
    start = time.perf_counter()
    resp = requests.post(f"{CH_URL}/?database={CH_DB}", data=full_query, timeout=30)
    resp.raise_for_status()
    elapsed = time.perf_counter() - start
    data = resp.json()
    return data.get("data", []), elapsed


def ch_table_size() -> int:
    """Get compressed size of benchmark_transactions in bytes."""
    query = ("SELECT sum(bytes_on_disk) as size FROM system.parts "
             "WHERE database = 'phoenix' AND table = 'benchmark_transactions' AND active = 1")
    resp = requests.post(f"{CH_URL}/", data=f"{query} FORMAT JSON", timeout=10)
    data = resp.json()
    rows = data.get("data", [])
    return int(rows[0]["size"]) if rows and rows[0]["size"] else 0


def ch_cleanup():
    ch_query_raw("DROP TABLE IF EXISTS benchmark_transactions", CH_DB)


# ── Benchmark Queries ──────────────────────────────────────────────────────

BENCHMARK_QUERIES = {
    "Monthly Aggregation": {
        "desc": "SUM(amount) GROUP BY month — time-series aggregation",
        "pg": """SELECT DATE_TRUNC('month', ts) as month,
                        SUM(ABS(amount)) as total, COUNT(*) as tx_count
                 FROM benchmark_transactions
                 GROUP BY DATE_TRUNC('month', ts) ORDER BY month""",
        "ch": """SELECT toStartOfMonth(ts) as month,
                        sum(abs(amount)) as total, count() as tx_count
                 FROM benchmark_transactions
                 GROUP BY month ORDER BY month""",
    },
    "Category Distribution": {
        "desc": "SUM by category — OLAP pivot/grouping query",
        "pg": """SELECT category_name, SUM(ABS(amount)) as total, COUNT(*) as cnt
                 FROM benchmark_transactions
                 GROUP BY category_name ORDER BY total DESC""",
        "ch": """SELECT category_name, sum(abs(amount)) as total, count() as cnt
                 FROM benchmark_transactions
                 GROUP BY category_name ORDER BY total DESC""",
    },
    "User Spending Trend": {
        "desc": "Per-user monthly average — sliding window analytics",
        "pg": f"""SELECT user_id, DATE_TRUNC('month', ts) as month,
                         AVG(ABS(amount)) as avg_spend
                  FROM benchmark_transactions
                  WHERE user_id = '{USER_IDS[0]}'
                  GROUP BY user_id, DATE_TRUNC('month', ts) ORDER BY month""",
        "ch": f"""SELECT user_id, toStartOfMonth(ts) as month,
                         avg(abs(amount)) as avg_spend
                  FROM benchmark_transactions
                  WHERE user_id = '{USER_IDS[0]}'
                  GROUP BY user_id, month ORDER BY month""",
    },
    "Top-N Spenders": {
        "desc": "Top 10 users by total spending — full table scan + sort",
        "pg": """SELECT user_id, SUM(ABS(amount)) as total_spent, COUNT(*) as tx_count
                 FROM benchmark_transactions
                 GROUP BY user_id ORDER BY total_spent DESC LIMIT 10""",
        "ch": """SELECT user_id, sum(abs(amount)) as total_spent, count() as tx_count
                 FROM benchmark_transactions
                 GROUP BY user_id ORDER BY total_spent DESC LIMIT 10""",
    },
    "Time Range Filter": {
        "desc": "Recent 3-month filter + aggregation — partition pruning advantage",
        "pg": """SELECT category_name, SUM(ABS(amount)) as total
                 FROM benchmark_transactions
                 WHERE ts >= NOW() - INTERVAL '3 months'
                 GROUP BY category_name ORDER BY total DESC""",
        "ch": """SELECT category_name, sum(abs(amount)) as total
                 FROM benchmark_transactions
                 WHERE ts >= today() - INTERVAL 3 MONTH
                 GROUP BY category_name ORDER BY total DESC""",
    },
}


# ── Benchmark Runner ───────────────────────────────────────────────────────

def run_benchmark():
    print("=" * 70)
    print("Phoenix Platform — ClickHouse vs PostgreSQL Benchmark")
    print("=" * 70)
    print(f"  Rows: {NUM_ROWS:,} | Query iterations: {QUERY_ITERATIONS}")
    print()

    # Generate data
    txns = generate_transactions(NUM_ROWS)

    # PostgreSQL setup
    print("\n[PostgreSQL] Connecting...")
    pg_conn = pg_connect()
    pg_setup_benchmark_table(pg_conn)

    # ClickHouse setup
    print("[ClickHouse] Connecting...")
    ch_setup_benchmark_table()

    # ── Insert Benchmark ───────────────────────────────────────────────
    print(f"\n── INSERT BENCHMARK ({NUM_ROWS:,} rows) ──")

    pg_insert_time = pg_insert(pg_conn, txns)
    print(f"  PostgreSQL: {pg_insert_time:.3f}s ({NUM_ROWS / pg_insert_time:,.0f} rows/s)")

    ch_insert_time = ch_insert(txns)
    print(f"  ClickHouse: {ch_insert_time:.3f}s ({NUM_ROWS / ch_insert_time:,.0f} rows/s)")

    # Allow ClickHouse to merge parts
    time.sleep(2)

    # ── Compression Benchmark ──────────────────────────────────────────
    print(f"\n── STORAGE COMPARISON ──")

    pg_size = pg_table_size(pg_conn)
    ch_size = ch_table_size()

    print(f"  PostgreSQL: {pg_size / 1024 / 1024:.2f} MB")
    print(f"  ClickHouse: {ch_size / 1024 / 1024:.2f} MB")
    if ch_size > 0:
        compression_ratio = pg_size / ch_size
        print(f"  Compression ratio: {compression_ratio:.1f}x (CH uses {compression_ratio:.1f}x less disk)")
    else:
        compression_ratio = 0
        print("  ClickHouse size is 0 — parts may not be flushed yet")

    # ── Query Benchmark ────────────────────────────────────────────────
    print(f"\n── QUERY BENCHMARK ({QUERY_ITERATIONS} iterations each) ──")

    query_results = {}
    for name, q in BENCHMARK_QUERIES.items():
        pg_times = []
        ch_times = []

        for _ in range(QUERY_ITERATIONS):
            _, pg_t = pg_query(pg_conn, q["pg"])
            pg_times.append(pg_t * 1000)  # Convert to ms

            _, ch_t = ch_query(q["ch"])
            ch_times.append(ch_t * 1000)

        pg_median = statistics.median(pg_times)
        ch_median = statistics.median(ch_times)
        speedup = pg_median / ch_median if ch_median > 0 else 0

        query_results[name] = {
            "description": q["desc"],
            "pg_median_ms": round(pg_median, 2),
            "ch_median_ms": round(ch_median, 2),
            "pg_p95_ms": round(sorted(pg_times)[int(0.95 * len(pg_times))], 2),
            "ch_p95_ms": round(sorted(ch_times)[int(0.95 * len(ch_times))], 2),
            "speedup": round(speedup, 2),
            "pg_all_ms": [round(t, 2) for t in pg_times],
            "ch_all_ms": [round(t, 2) for t in ch_times],
        }

        marker = "OK" if speedup > 1 else "WARN" if speedup == 1 else "FAIL"
        print(f"\n  {marker} {name}: {q['desc']}")
        print(f"     PostgreSQL: {pg_median:.2f}ms (p95: {query_results[name]['pg_p95_ms']:.2f}ms)")
        print(f"     ClickHouse: {ch_median:.2f}ms (p95: {query_results[name]['ch_p95_ms']:.2f}ms)")
        print(f"     Speedup:    {speedup:.2f}x")

    # ── Results ────────────────────────────────────────────────────────
    results = {
        "timestamp": datetime.now().isoformat(),
        "config": {"rows": NUM_ROWS, "iterations": QUERY_ITERATIONS, "users": len(USER_IDS)},
        "insert": {
            "pg_seconds": round(pg_insert_time, 3),
            "ch_seconds": round(ch_insert_time, 3),
            "pg_rows_per_sec": round(NUM_ROWS / pg_insert_time),
            "ch_rows_per_sec": round(NUM_ROWS / ch_insert_time),
        },
        "storage": {
            "pg_bytes": pg_size,
            "ch_bytes": ch_size,
            "compression_ratio": round(compression_ratio, 2),
        },
        "queries": query_results,
    }

    # Save JSON logs
    json_path = RESULTS_DIR / "benchmark_results.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved to {json_path}")

    # Generate HTML report
    html_path = generate_html_report(results)
    print(f"  HTML report saved to {html_path}")

    # Cleanup
    print("\n── CLEANUP ──")
    pg_cleanup(pg_conn)
    ch_cleanup()
    pg_conn.close()
    print("  Benchmark tables dropped from both databases.")
    print("\n" + "=" * 70)
    print("BENCHMARK COMPLETE")
    print("=" * 70)

    return results


# ── HTML Report Generator ──────────────────────────────────────────────────

def generate_html_report(results: dict) -> Path:
    """Generate a self-contained HTML report with embedded CSS charts."""
    queries = results["queries"]
    storage = results["storage"]
    insert = results["insert"]
    config = results["config"]

    # Build bar chart rows
    query_bars = ""
    for name, q in queries.items():
        pg_ms = q["pg_median_ms"]
        ch_ms = q["ch_median_ms"]
        max_ms = max(pg_ms, ch_ms, 1)
        pg_pct = (pg_ms / max_ms) * 100
        ch_pct = (ch_ms / max_ms) * 100
        speedup = q["speedup"]
        speedup_color = "#22c55e" if speedup > 1.5 else "#eab308" if speedup > 1 else "#ef4444"

        query_bars += f"""
        <div class="query-block">
            <div class="query-header">
                <h3>{name}</h3>
                <span class="speedup" style="background:{speedup_color}">{speedup:.1f}x faster</span>
            </div>
            <p class="query-desc">{q['description']}</p>
            <div class="bar-group">
                <div class="bar-row">
                    <span class="bar-label">PostgreSQL</span>
                    <div class="bar-track">
                        <div class="bar pg-bar" style="width:{pg_pct}%"></div>
                    </div>
                    <span class="bar-value">{pg_ms:.1f}ms</span>
                </div>
                <div class="bar-row">
                    <span class="bar-label">ClickHouse</span>
                    <div class="bar-track">
                        <div class="bar ch-bar" style="width:{ch_pct}%"></div>
                    </div>
                    <span class="bar-value">{ch_ms:.1f}ms</span>
                </div>
            </div>
        </div>
        """

    # Compression visual
    pg_mb = storage["pg_bytes"] / 1024 / 1024
    ch_mb = storage["ch_bytes"] / 1024 / 1024 if storage["ch_bytes"] > 0 else 0.01
    cr = storage["compression_ratio"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Phoenix — ClickHouse vs PostgreSQL Benchmark Report</title>
<style>
    :root {{
        --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
        --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8;
        --pg-color: #6366f1; --ch-color: #22c55e;
        --success: #22c55e; --warning: #eab308; --danger: #ef4444;
    }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ background:var(--bg); color:var(--text); font-family:'Inter','Segoe UI',sans-serif;
           line-height:1.6; padding:2rem; max-width:1100px; margin:0 auto; }}
    h1 {{ font-size:2rem; margin-bottom:0.5rem; background:linear-gradient(135deg,var(--accent),#a78bfa);
         -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
    h2 {{ font-size:1.3rem; margin:2rem 0 1rem; color:var(--accent); }}
    h3 {{ font-size:1rem; color:var(--text); }}
    .subtitle {{ color:var(--muted); font-size:0.9rem; margin-bottom:2rem; }}
    .card {{ background:var(--surface); border-radius:12px; padding:1.5rem; margin-bottom:1.5rem;
             border:1px solid var(--surface2); }}
    .stats-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:1rem; }}
    .stat {{ background:var(--surface2); border-radius:10px; padding:1.2rem; text-align:center; }}
    .stat-value {{ font-size:1.8rem; font-weight:700; }}
    .stat-label {{ color:var(--muted); font-size:0.8rem; text-transform:uppercase; letter-spacing:0.05em; }}
    .pg-color {{ color:var(--pg-color); }} .ch-color {{ color:var(--ch-color); }}
    .query-block {{ background:var(--surface2); border-radius:10px; padding:1.2rem; margin-bottom:1rem; }}
    .query-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:0.3rem; }}
    .query-desc {{ color:var(--muted); font-size:0.82rem; margin-bottom:0.8rem; }}
    .speedup {{ font-size:0.75rem; font-weight:600; color:#fff; padding:3px 10px; border-radius:20px; }}
    .bar-group {{ display:flex; flex-direction:column; gap:6px; }}
    .bar-row {{ display:flex; align-items:center; gap:8px; }}
    .bar-label {{ width:90px; font-size:0.78rem; color:var(--muted); text-align:right; }}
    .bar-track {{ flex:1; background:var(--surface); border-radius:6px; height:22px; overflow:hidden; }}
    .bar {{ height:100%; border-radius:6px; transition:width 0.5s ease; min-width:2px; }}
    .pg-bar {{ background:linear-gradient(90deg,var(--pg-color),#818cf8); }}
    .ch-bar {{ background:linear-gradient(90deg,var(--ch-color),#4ade80); }}
    .bar-value {{ width:70px; font-size:0.78rem; font-weight:600; }}
    .storage-visual {{ display:flex; gap:1.5rem; align-items:flex-end; justify-content:center; padding:1rem; }}
    .storage-bar {{ display:flex; flex-direction:column; align-items:center; gap:0.5rem; }}
    .storage-block {{ border-radius:8px; width:120px; transition:height 0.5s ease; }}
    .storage-label {{ font-size:0.8rem; color:var(--muted); }}
    .storage-size {{ font-weight:700; font-size:1rem; }}
    .adr-note {{ background:#1a2332; border-left:3px solid var(--accent); padding:1rem 1.2rem;
                 border-radius:0 8px 8px 0; margin:1.5rem 0; font-size:0.85rem; }}
    .adr-note strong {{ color:var(--accent); }}
    table {{ width:100%; border-collapse:collapse; font-size:0.85rem; }}
    th {{ text-align:left; padding:10px 12px; color:var(--muted); border-bottom:1px solid var(--surface2); }}
    td {{ padding:10px 12px; border-bottom:1px solid rgba(255,255,255,0.05); }}
    .legend {{ display:flex; gap:1.5rem; margin:1rem 0; font-size:0.82rem; }}
    .legend-item {{ display:flex; align-items:center; gap:6px; }}
    .legend-dot {{ width:12px; height:12px; border-radius:50%; }}
    footer {{ text-align:center; color:var(--muted); font-size:0.75rem; margin-top:3rem; }}
</style>
</head>
<body>
<h1>⚡ ClickHouse vs PostgreSQL</h1>
<p class="subtitle">Phoenix Financial Analytics Platform — ADR-002 Polyglot Persistence Benchmark<br>
   Generated: {results['timestamp']} | Dataset: {config['rows']:,} transactions, {config['users']} users</p>

<div class="adr-note">
    <strong>ADR-002:</strong> PostgreSQL provides ACID guarantees for OLTP (transactional reads/writes).
    ClickHouse handles OLAP (analytical aggregations, time-series queries) using columnar storage,
    compression, and partition pruning. This benchmark validates the performance separation.
</div>

<h2>📊 Key Metrics</h2>
<div class="stats-grid">
    <div class="stat">
        <div class="stat-value" style="color:var(--ch-color)">{cr:.1f}x</div>
        <div class="stat-label">Compression Ratio</div>
    </div>
    <div class="stat">
        <div class="stat-value pg-color">{pg_mb:.1f} MB</div>
        <div class="stat-label">PostgreSQL Disk Usage</div>
    </div>
    <div class="stat">
        <div class="stat-value ch-color">{ch_mb:.1f} MB</div>
        <div class="stat-label">ClickHouse Disk Usage</div>
    </div>
    <div class="stat">
        <div class="stat-value" style="color:var(--accent)">{config['rows']:,}</div>
        <div class="stat-label">Transactions Tested</div>
    </div>
</div>

<h2>🚀 Insert Throughput</h2>
<div class="card">
    <div class="stats-grid">
        <div class="stat">
            <div class="stat-value pg-color">{insert['pg_rows_per_sec']:,}</div>
            <div class="stat-label">PostgreSQL rows/sec</div>
        </div>
        <div class="stat">
            <div class="stat-value ch-color">{insert['ch_rows_per_sec']:,}</div>
            <div class="stat-label">ClickHouse rows/sec</div>
        </div>
        <div class="stat">
            <div class="stat-value pg-color">{insert['pg_seconds']:.2f}s</div>
            <div class="stat-label">PostgreSQL Insert Time</div>
        </div>
        <div class="stat">
            <div class="stat-value ch-color">{insert['ch_seconds']:.2f}s</div>
            <div class="stat-label">ClickHouse Insert Time</div>
        </div>
    </div>
</div>

<h2>💾 Storage & Compression</h2>
<div class="card">
    <p style="color:var(--muted);font-size:0.85rem;margin-bottom:1rem;">
        ClickHouse uses columnar storage with LZ4/ZSTD compression. Identical data stored in both databases:
    </p>
    <div class="storage-visual">
        <div class="storage-bar">
            <div class="storage-block" style="height:{min(200, max(40, 200))}px;background:linear-gradient(180deg,var(--pg-color),#818cf8);"></div>
            <div class="storage-size pg-color">{pg_mb:.1f} MB</div>
            <div class="storage-label">PostgreSQL</div>
        </div>
        <div class="storage-bar">
            <div class="storage-block" style="height:{max(20, min(200, int(200 / max(cr, 1))))}px;background:linear-gradient(180deg,var(--ch-color),#4ade80);"></div>
            <div class="storage-size ch-color">{ch_mb:.1f} MB</div>
            <div class="storage-label">ClickHouse</div>
        </div>
    </div>
    <p style="text-align:center;margin-top:0.5rem;font-size:0.9rem;">
        ClickHouse achieves <strong style="color:var(--ch-color)">{cr:.1f}x compression</strong> through
        columnar storage + LZ4 compression
    </p>
</div>

<h2>⏱️ Query Latency Comparison</h2>
<div class="card">
    <div class="legend">
        <div class="legend-item"><div class="legend-dot" style="background:var(--pg-color)"></div> PostgreSQL (OLTP)</div>
        <div class="legend-item"><div class="legend-dot" style="background:var(--ch-color)"></div> ClickHouse (OLAP)</div>
    </div>
    {query_bars}
</div>

<h2>📋 Detailed Results</h2>
<div class="card">
    <table>
        <thead>
            <tr><th>Query</th><th>PG Median</th><th>CH Median</th><th>PG p95</th><th>CH p95</th><th>Speedup</th></tr>
        </thead>
        <tbody>
            {"".join(f'<tr><td>{name}</td><td>{q["pg_median_ms"]:.1f}ms</td><td>{q["ch_median_ms"]:.1f}ms</td><td>{q["pg_p95_ms"]:.1f}ms</td><td>{q["ch_p95_ms"]:.1f}ms</td><td style="color:{"var(--ch-color)" if q["speedup"]>1 else "var(--danger)"}">{q["speedup"]:.1f}x</td></tr>' for name, q in queries.items())}
        </tbody>
    </table>
</div>

<h2>🏗️ Why ClickHouse Wins for Analytics</h2>
<div class="card" style="font-size:0.88rem;">
    <table>
        <thead><tr><th>Feature</th><th>PostgreSQL</th><th>ClickHouse</th></tr></thead>
        <tbody>
            <tr><td>Storage Model</td><td>Row-based</td><td style="color:var(--ch-color)">Columnar</td></tr>
            <tr><td>Compression</td><td>TOAST (page-level)</td><td style="color:var(--ch-color)">LZ4/ZSTD per-column</td></tr>
            <tr><td>Aggregations</td><td>Scans all columns</td><td style="color:var(--ch-color)">Reads only needed columns</td></tr>
            <tr><td>Partitioning</td><td>Manual partition tables</td><td style="color:var(--ch-color)">Native PARTITION BY, auto-pruning</td></tr>
            <tr><td>ACID Transactions</td><td style="color:var(--pg-color)">Full ACID</td><td>Eventual consistency</td></tr>
            <tr><td>Ideal Workload</td><td style="color:var(--pg-color)">OLTP (single row R/W)</td><td style="color:var(--ch-color)">OLAP (bulk analytics)</td></tr>
        </tbody>
    </table>
</div>

<footer>
    Phoenix Financial Analytics Platform — ADR-002 Benchmark Report<br>
    Team 23 | Generated {results['timestamp']}
</footer>
</body>
</html>"""

    html_path = RESULTS_DIR / "benchmark_report.html"
    with open(html_path, "w") as f:
        f.write(html)
    return html_path


# ── Entry Point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_benchmark()
