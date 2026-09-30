#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# run_comparison.sh — Automates the NFR comparison between architectures
# ──────────────────────────────────────────────────────────────────────────────
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ALT_DIR="$PROJECT_ROOT/ALTERNATE_ARCH"
INFRA_DIR="$PROJECT_ROOT/infra"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Phoenix — Architecture NFR Comparison                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Phase 1: Benchmark Monolith ──────────────────────────────────────────────
echo "▶ Phase 1: Starting Monolith..."
cd "$ALT_DIR"
sudo docker compose down -v 2>/dev/null || true
sudo docker compose up -d --build
echo "  Waiting for monolith health check..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:9000/health/ready > /dev/null 2>&1; then
        echo "  ✓ Monolith is healthy"
        break
    fi
    sleep 2
done

echo ""
echo "▶ Running benchmarks against Monolith..."
python3 "$ALT_DIR/benchmark.py" --arch monolith --base-url http://localhost:9000 --skip-fault
echo ""

# ── Phase 2: Benchmark Microservices ─────────────────────────────────────────
echo "▶ Phase 2: Stopping Monolith, Starting Microservices..."
cd "$ALT_DIR"
sudo docker compose down -v 2>/dev/null || true

cd "$INFRA_DIR"
sudo docker compose up -d --build
echo "  Waiting for microservices health checks..."
for i in $(seq 1 60); do
    if curl -sf -k https://localhost/api/v1/auth/health/ready > /dev/null 2>&1; then
        echo "  ✓ Microservices are healthy"
        break
    fi
    sleep 2
done

echo ""
echo "▶ Running benchmarks against Microservices..."
python3 "$ALT_DIR/benchmark.py" --arch microservices --base-url https://localhost --skip-fault
echo ""

# ── Phase 3: Summary ─────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Comparison Complete                                       ║"
echo "║                                                             ║"
echo "║   Results saved to:                                         ║"
echo "║     nfr_comparison_monolith.json                            ║"
echo "║     nfr_comparison_microservices.json                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
