"""Locust load testing for Monolith NFR benchmarks.
Mirrors the microservices nfr_locustfile.py but targets the monolith API."""

from locust import HttpUser, task, between, LoadTestShape
import random
import uuid


class MonolithCacheUser(HttpUser):
    """
    NFR-01: Monolith has NO cache — every call hits the DB.
    This measures the raw PostgreSQL latency without any caching layer.
    """
    wait_time = between(1, 2)
    host = "http://localhost:9000"

    def on_start(self):
        self.email = f"monolith_bench_{uuid.uuid4().hex[:8]}@test.com"
        self.password = "TestPassword123!"

        # Register
        self.client.post("/api/v1/auth/register", json={
            "email": self.email,
            "display_name": "Monolith Bench User",
            "password": self.password,
        })

        # Login
        response = self.client.post("/api/v1/auth/login", json={
            "email": self.email,
            "password": self.password,
        })

        if response.status_code == 200:
            self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
            # First call (no cache benefit — DB hit every time)
            self.client.get(
                "/api/v1/dashboard/overview",
                headers=self.headers,
                name="GET /dashboard/overview (initial)",
            )
        else:
            self.headers = {}

    @task
    def dashboard_no_cache(self):
        """Every call hits PostgreSQL — no Redis cache layer."""
        self.client.get(
            "/api/v1/dashboard/overview",
            headers=self.headers,
            name="GET /dashboard/overview (no cache)",
        )


class MonolithScalabilityUser(HttpUser):
    """NFR-02: Throughput test for the monolith."""
    wait_time = between(0.1, 0.2)
    host = "http://localhost:9000"

    def on_start(self):
        self.email = f"monolith_scale_{uuid.uuid4().hex[:8]}@test.com"
        self.password = "TestPassword123!"

        self.client.post("/api/v1/auth/register", json={
            "email": self.email,
            "display_name": "Monolith Scale User",
            "password": self.password,
        })

        response = self.client.post("/api/v1/auth/login", json={
            "email": self.email,
            "password": self.password,
        })
        if response.status_code == 200:
            self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        else:
            self.headers = {}

    @task(3)
    def dashboard_overview(self):
        self.client.get(
            "/api/v1/dashboard/overview",
            headers=self.headers,
            name="GET /dashboard/overview",
        )

    @task(1)
    def add_transaction(self):
        self.client.post("/api/v1/transactions/manual", json={
            "amount": round(random.uniform(10, 500), 2),
            "description": "Scalability transaction",
            "currency": "INR",
        }, headers=self.headers, name="POST /transactions/manual")


class MonolithStepLoad(LoadTestShape):
    """Step load: 50 → 300 users over 180s."""
    step_time = 30
    step_load = 50
    spawn_rate = 10
    time_limit = 180

    def tick(self):
        run_time = self.get_run_time()
        if run_time > self.time_limit:
            return None
        current_step = int(run_time / self.step_time) + 1
        return (current_step * self.step_load, self.spawn_rate)
