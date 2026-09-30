"""Locust load testing for Non-Functional Requirements (NFRs).
Benchmarks NFR-01 (Performance) and NFR-02 (Scalability)."""

from locust import HttpUser, task, between, LoadTestShape
import random
import uuid

class NFR01CacheHitUser(HttpUser):
    """
    Simulates NFR-01 Cache Hit scenario.
    Repeatedly accesses the dashboard overview to measure p95 latency.
    """
    wait_time = between(1, 2)
    host = "https://localhost"
    
    def on_start(self):
        self.email = f"loadtest_hit_{uuid.uuid4().hex[:8]}@test.com"
        self.password = "TestPassword123!"
        
        # Register
        self.client.post("/api/v1/auth/register", json={
            "email": self.email,
            "display_name": "NFR Cache Hit User",
            "password": self.password,
        }, verify=False)
        
        # Login
        response = self.client.post("/api/v1/auth/login", json={
            "email": self.email,
            "password": self.password
        }, verify=False)
        
        if response.status_code == 200:
            self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
            # Initial call to populate cache
            self.client.get("/api/v1/dashboard/overview", headers=self.headers, verify=False, name="GET /dashboard/overview (initial)")
        else:
            self.headers = {}

    @task
    def dashboard_cache_hit(self):
        self.client.get("/api/v1/dashboard/overview", headers=self.headers, verify=False, name="GET /dashboard/overview (cache hit)")


class NFR01ColdCacheUser(HttpUser):
    """
    Simulates NFR-01 Cache Miss (cold cache) scenario.
    Registers a new user, logs in, and fetches the dashboard exactly once.
    """
    host = "https://localhost"
    
    @task
    def dashboard_cold_cache(self):
        email = f"loadtest_miss_{uuid.uuid4().hex[:8]}@test.com"
        password = "TestPassword123!"
        
        # Register
        self.client.post("/api/v1/auth/register", json={
            "email": email,
            "display_name": "NFR Cold Cache User",
            "password": password,
        }, verify=False, name="POST /auth/register")
        
        # Login
        response = self.client.post("/api/v1/auth/login", json={
            "email": email,
            "password": password
        }, verify=False, name="POST /auth/login")
        
        if response.status_code == 200:
            headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
            self.client.get("/api/v1/dashboard/overview", headers=headers, verify=False, name="GET /dashboard/overview (cache miss)")
        
        # Sleep to keep the user alive without generating more requests, preventing Locust respawns
        import gevent
        while True:
            gevent.sleep(1)

class NFR02ScalabilityUser(HttpUser):
    """
    Simulates NFR-02 Scalability scenario.
    Mix of read and write endpoints to test sustained throughput.
    """
    wait_time = between(0.1, 0.2)
    host = "https://localhost"
    
    def on_start(self):
        self.email = f"loadtest_scale_{uuid.uuid4().hex[:8]}@test.com"
        self.password = "TestPassword123!"
        
        self.client.post("/api/v1/auth/register", json={
            "email": self.email, "display_name": "NFR Scalability User", "password": self.password,
        }, verify=False)
        
        response = self.client.post("/api/v1/auth/login", json={"email": self.email, "password": self.password}, verify=False)
        if response.status_code == 200:
            self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        else:
            self.headers = {}

    @task(3)
    def dashboard_overview(self):
        self.client.get("/api/v1/dashboard/overview", headers=self.headers, verify=False, name="GET /dashboard/overview")

    @task(1)
    def add_transaction(self):
        self.client.post("/api/v1/transactions/manual", json={
            "amount": round(random.uniform(10, 500), 2),
            "description": f"Scalability transaction",
            "currency": "USD"
        }, headers=self.headers, verify=False, name="POST /transactions/manual")


class StepLoadShape(LoadTestShape):
    """
    A step load shape for NFR-02 Scalability: 50 -> 300 RPS.
    """
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
