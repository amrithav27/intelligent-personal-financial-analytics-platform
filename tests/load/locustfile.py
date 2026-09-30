"""Locust load testing — simulates concurrent users hitting Phoenix APIs."""

from locust import HttpUser, task, between


class PhoenixUser(HttpUser):
    wait_time = between(1, 3)
    host = "https://localhost"

    def on_start(self):
        """Register and login to get a JWT token."""
        import random
        self.email = f"loadtest_{random.randint(0, 999999)}@test.com"
        self.password = "TestPassword123!"

        # Register
        response = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": self.email,
                "display_name": "Load Test User",
                "password": self.password,
            },
            verify=False,
        )
        if response.status_code in (201, 409):
            # Login
            response = self.client.post(
                "/api/v1/auth/login",
                json={"email": self.email, "password": self.password},
                verify=False,
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data["access_token"]
                self.headers = {"Authorization": f"Bearer {self.token}"}
            else:
                self.token = None
                self.headers = {}
        else:
            self.token = None
            self.headers = {}

    @task(5)
    def dashboard_overview(self):
        """Most frequent — dashboard loads."""
        self.client.get(
            "/api/v1/dashboard/overview",
            headers=self.headers,
            verify=False,
        )

    @task(3)
    def list_transactions(self):
        """Transaction listing."""
        self.client.get(
            "/api/v1/transactions?page=1&page_size=20",
            headers=self.headers,
            verify=False,
        )

    @task(2)
    def fhs_history(self):
        """FHS score history."""
        self.client.get(
            "/api/v1/analytics/fhs/history?months=6",
            headers=self.headers,
            verify=False,
        )

    @task(2)
    def category_distribution(self):
        """Category spending distribution."""
        self.client.get(
            "/api/v1/analytics/categories",
            headers=self.headers,
            verify=False,
        )

    @task(1)
    def budget_recommendations(self):
        """Budget recommendations."""
        self.client.get(
            "/api/v1/recommendations/budget",
            headers=self.headers,
            verify=False,
        )

    @task(1)
    def ingest_manual(self):
        """Manual transaction ingestion."""
        import random
        self.client.post(
            "/api/v1/transactions/manual",
            json={
                "amount": round(random.uniform(50, 5000), 2),
                "description": f"Load test transaction {random.randint(0, 99999)}",
                "currency": "INR",
            },
            headers=self.headers,
            verify=False,
        )
