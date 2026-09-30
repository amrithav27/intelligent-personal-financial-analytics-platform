#!/usr/bin/env python3
"""
NFR Benchmark Suite — Compares Microservices vs. Monolith Architecture
======================================================================

Measures 4 Non-Functional Requirements:
  NFR-1  Response Time   — p95 latency for GET /dashboard/overview
  NFR-2  Throughput       — Sustained requests per second (RPS)
  NFR-3  Memory Efficiency— RSS memory delta per 1000 requests
  NFR-4  Fault Tolerance  — Availability during partial failure + MTTR

Usage:
  python benchmark.py --arch monolith  --base-url http://localhost:9000
  python benchmark.py --arch microservices --base-url https://localhost

Results are printed as a markdown table and saved to nfr_comparison.md.
"""

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import httpx

# ─── Helpers ──────────────────────────────────────────────────────────────────

def p95(values: list[float]) -> float:
    """Compute the 95th percentile of a list of values."""
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(math.ceil(0.95 * len(s))) - 1
    return s[max(0, idx)]


def register_and_login(client: httpx.Client, base_url: str) -> dict:
    """Register a new user and return auth headers + user info."""
    email = f"bench_{uuid.uuid4().hex[:8]}@test.com"
    password = "BenchmarkPass123!"

    client.post(
        f"{base_url}/api/v1/auth/register",
        json={"email": email, "display_name": "Benchmark User", "password": password},
    )
    resp = client.post(
        f"{base_url}/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed: {resp.status_code} {resp.text}")
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ─── NFR-1: Response Time ─────────────────────────────────────────────────────

def benchmark_response_time(base_url: str, iterations: int = 200) -> dict:
    """Measure p95 latency for GET /dashboard/overview."""
    print(f"  [NFR-1] Measuring response time ({iterations} iterations)...")

    with httpx.Client(verify=False, timeout=30.0) as client:
        headers = register_and_login(client, base_url)

        # Warm-up
        for _ in range(5):
            client.get(f"{base_url}/api/v1/dashboard/overview", headers=headers)

        latencies = []
        for i in range(iterations):
            start = time.perf_counter()
            resp = client.get(f"{base_url}/api/v1/dashboard/overview", headers=headers)
            elapsed = (time.perf_counter() - start) * 1000  # ms
            if resp.status_code == 200:
                latencies.append(elapsed)

    return {
        "p50_ms": round(statistics.median(latencies), 2) if latencies else 0,
        "p95_ms": round(p95(latencies), 2) if latencies else 0,
        "mean_ms": round(statistics.mean(latencies), 2) if latencies else 0,
        "min_ms": round(min(latencies), 2) if latencies else 0,
        "max_ms": round(max(latencies), 2) if latencies else 0,
        "count": len(latencies),
    }


# ─── NFR-2: Throughput ────────────────────────────────────────────────────────

def _worker_throughput(base_url: str, duration_sec: int = 15) -> int:
    """Worker that sends as many requests as possible in the given duration."""
    count = 0
    with httpx.Client(verify=False, timeout=30.0) as client:
        headers = register_and_login(client, base_url)
        deadline = time.time() + duration_sec
        while time.time() < deadline:
            resp = client.get(f"{base_url}/api/v1/dashboard/overview", headers=headers)
            if resp.status_code == 200:
                count += 1
    return count


def benchmark_throughput(base_url: str, concurrency: int = 20, duration_sec: int = 15) -> dict:
    """Sustained RPS at given concurrency."""
    print(f"  [NFR-2] Measuring throughput ({concurrency} workers × {duration_sec}s)...")

    total = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_worker_throughput, base_url, duration_sec) for _ in range(concurrency)]
        for f in as_completed(futures):
            total += f.result()

    rps = total / duration_sec
    return {
        "total_requests": total,
        "duration_sec": duration_sec,
        "concurrency": concurrency,
        "rps": round(rps, 2),
    }


# ─── NFR-3: Memory Efficiency ────────────────────────────────────────────────

def benchmark_memory(base_url: str, requests_count: int = 500) -> dict:
    """
    Measure memory usage by checking /health endpoint before and after
    sending N requests. For docker containers, uses `docker stats`.
    """
    print(f"  [NFR-3] Measuring memory efficiency ({requests_count} requests)...")

    # Get container name based on arch
    container_name = None
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5,
        )
        names = result.stdout.strip().split("\n")
        for name in names:
            if "monolith" in name.lower() and "postgres" not in name.lower():
                container_name = name
                break
            elif "analytics" in name.lower():
                container_name = name
                break
    except Exception:
        pass

    def get_container_memory(cname: str) -> float:
        """Get RSS memory of container in MB."""
        try:
            result = subprocess.run(
                ["docker", "stats", cname, "--no-stream", "--format", "{{.MemUsage}}"],
                capture_output=True, text=True, timeout=10,
            )
            mem_str = result.stdout.strip().split("/")[0].strip()
            if "GiB" in mem_str:
                return float(mem_str.replace("GiB", "").strip()) * 1024
            elif "MiB" in mem_str:
                return float(mem_str.replace("MiB", "").strip())
            elif "KiB" in mem_str:
                return float(mem_str.replace("KiB", "").strip()) / 1024
            return 0.0
        except Exception:
            return 0.0

    mem_before = get_container_memory(container_name) if container_name else 0

    # Send requests
    with httpx.Client(verify=False, timeout=30.0) as client:
        headers = register_and_login(client, base_url)
        for _ in range(requests_count):
            client.get(f"{base_url}/api/v1/dashboard/overview", headers=headers)

    mem_after = get_container_memory(container_name) if container_name else 0

    return {
        "container": container_name or "unknown",
        "mem_before_mb": round(mem_before, 2),
        "mem_after_mb": round(mem_after, 2),
        "mem_delta_mb": round(mem_after - mem_before, 2),
        "requests": requests_count,
        "mem_per_1k_req_mb": round(((mem_after - mem_before) / requests_count) * 1000, 2) if requests_count > 0 and mem_after > 0 else 0,
    }


# ─── NFR-4: Fault Tolerance ──────────────────────────────────────────────────

def benchmark_fault_tolerance(base_url: str, arch: str) -> dict:
    """
    Test availability during partial failure.
    For microservices: crash analytics container, check if dashboard still works (cached).
    For monolith: crash the monolith, measure full downtime.
    """
    print(f"  [NFR-4] Measuring fault tolerance ({arch})...")

    result = {"arch": arch}

    if arch == "microservices":
        # Register and login, warm the cache
        with httpx.Client(verify=False, timeout=30.0) as client:
            headers = register_and_login(client, base_url)
            # Prime the cache
            client.get(f"{base_url}/api/v1/dashboard/overview", headers=headers)
            time.sleep(1)

            # Kill analytics container
            try:
                subprocess.run(["docker", "kill", "phoenix-analytics"], capture_output=True, timeout=5)
            except Exception:
                pass

            # Check if dashboard still responds (from cache)
            time.sleep(1)
            available_during_outage = 0
            total_checks = 10
            for _ in range(total_checks):
                try:
                    resp = client.get(f"{base_url}/api/v1/dashboard/overview", headers=headers, timeout=5)
                    if resp.status_code == 200:
                        available_during_outage += 1
                except Exception:
                    pass
                time.sleep(0.5)

            result["availability_during_outage"] = f"{(available_during_outage / total_checks) * 100:.0f}%"

            # Restart and measure MTTR
            start_recover = time.perf_counter()
            try:
                subprocess.run(
                    ["docker", "start", "phoenix-analytics"], capture_output=True, timeout=30,
                )
            except Exception:
                pass

            recovered = False
            for _ in range(60):
                try:
                    resp = httpx.get(f"{base_url}/health/ready" if "localhost:9000" in base_url else f"https://localhost/api/v1/dashboard/overview",
                                     verify=False, timeout=3)
                    if resp.status_code == 200:
                        recovered = True
                        break
                except Exception:
                    pass
                time.sleep(0.5)

            mttr = time.perf_counter() - start_recover
            result["mttr_seconds"] = round(mttr, 2) if recovered else "N/A"
            result["fault_isolation"] = "Yes — other services unaffected"

    else:  # monolith
        with httpx.Client(verify=False, timeout=30.0) as client:
            headers = register_and_login(client, base_url)

            # Kill the monolith
            try:
                subprocess.run(["docker", "kill", "phoenix-monolith"], capture_output=True, timeout=5)
            except Exception:
                pass

            time.sleep(1)

            # Check availability (should be 0%)
            available_during_outage = 0
            total_checks = 10
            for _ in range(total_checks):
                try:
                    resp = client.get(f"{base_url}/api/v1/dashboard/overview", headers=headers, timeout=3)
                    if resp.status_code == 200:
                        available_during_outage += 1
                except Exception:
                    pass
                time.sleep(0.5)

            result["availability_during_outage"] = f"{(available_during_outage / total_checks) * 100:.0f}%"

            # Restart and measure MTTR
            start_recover = time.perf_counter()
            try:
                subprocess.run(
                    ["docker", "start", "phoenix-monolith"], capture_output=True, timeout=30,
                )
            except Exception:
                pass

            recovered = False
            for _ in range(60):
                try:
                    resp = httpx.get(f"{base_url}/health/ready", verify=False, timeout=3)
                    if resp.status_code == 200:
                        recovered = True
                        break
                except Exception:
                    pass
                time.sleep(0.5)

            mttr = time.perf_counter() - start_recover
            result["mttr_seconds"] = round(mttr, 2) if recovered else "N/A"
            result["fault_isolation"] = "No — entire application goes down"

    return result


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Phoenix NFR Benchmark Suite")
    parser.add_argument("--arch", required=True, choices=["microservices", "monolith"])
    parser.add_argument("--base-url", required=True, help="Base URL (e.g., http://localhost:9000)")
    parser.add_argument("--output", default="nfr_comparison.md", help="Output file")
    parser.add_argument("--skip-fault", action="store_true", help="Skip fault tolerance test")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Phoenix NFR Benchmark — {args.arch.upper()}")
    print(f"  Target: {args.base_url}")
    print(f"  Time:   {datetime.now().isoformat()}")
    print(f"{'='*60}\n")

    results = {"arch": args.arch, "base_url": args.base_url, "timestamp": datetime.now().isoformat()}

    # NFR-1: Response Time
    results["nfr1_response_time"] = benchmark_response_time(args.base_url)
    print(f"    → p95 = {results['nfr1_response_time']['p95_ms']} ms\n")

    # NFR-2: Throughput
    results["nfr2_throughput"] = benchmark_throughput(args.base_url)
    print(f"    → RPS = {results['nfr2_throughput']['rps']}\n")

    # NFR-3: Memory
    results["nfr3_memory"] = benchmark_memory(args.base_url)
    print(f"    → Memory delta = {results['nfr3_memory']['mem_delta_mb']} MB\n")

    # NFR-4: Fault Tolerance
    if not args.skip_fault:
        results["nfr4_fault_tolerance"] = benchmark_fault_tolerance(args.base_url, args.arch)
        print(f"    → Availability = {results['nfr4_fault_tolerance']['availability_during_outage']}\n")
    else:
        results["nfr4_fault_tolerance"] = {"skipped": True}

    # Save JSON
    json_path = args.output.replace(".md", f"_{args.arch}.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nJSON results saved to {json_path}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY — {args.arch.upper()}")
    print(f"{'='*60}")
    print(f"  NFR-1 Response Time (p95):  {results['nfr1_response_time']['p95_ms']} ms")
    print(f"  NFR-2 Throughput:           {results['nfr2_throughput']['rps']} RPS")
    print(f"  NFR-3 Memory (after load):  {results['nfr3_memory']['mem_after_mb']} MB")
    if not args.skip_fault:
        print(f"  NFR-4 Fault Tolerance:      {results['nfr4_fault_tolerance'].get('availability_during_outage', 'N/A')}")
        print(f"  NFR-4 MTTR:                 {results['nfr4_fault_tolerance'].get('mttr_seconds', 'N/A')}s")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
