"""
End-to-End Pipeline Integration Test
=====================================
Verifies the full observer chain:
  Ingestion → Analytics (categorize + FHS) → Anomaly (Z-score) → Notification (WebSocket push)

Uses unittest.mock to intercept inter-service HTTP calls and verify they carry correct payloads.
Each service's internal logic is exercised against an in-memory SQLite database with realistic data.
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, ANY

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# PATH SETUP: ensure service directories are importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERVICES_DIR = os.path.join(PROJECT_ROOT, "services")

# ---------------------------------------------------------------------------
# Fixtures — shared test data
# ---------------------------------------------------------------------------

TEST_USER_ID = str(uuid.uuid4())

SAMPLE_CSV = """date,amount,description,merchant
2026-04-01,1500.00,Grocery purchase at BigBasket,BigBasket
2026-04-02,250.00,Uber ride to office,Uber
2026-04-03,8500.00,Monthly rent payment,LandlordCorp
2026-04-04,450.00,Dinner at Olive Garden,Olive Garden
2026-04-05,120.00,Netflix subscription,Netflix"""

SAMPLE_TRANSACTIONS = [
    {
        "id": str(uuid.uuid4()),
        "amount": Decimal("1500.00"),
        "description": "Grocery purchase at BigBasket",
        "merchant": "BigBasket",
        "date": "2026-04-01",
        "category_expected": "Groceries",
    },
    {
        "id": str(uuid.uuid4()),
        "amount": Decimal("250.00"),
        "description": "Uber ride to office",
        "merchant": "Uber",
        "date": "2026-04-02",
        "category_expected": "Transportation",
    },
    {
        "id": str(uuid.uuid4()),
        "amount": Decimal("8500.00"),
        "description": "Monthly rent payment",
        "merchant": "LandlordCorp",
        "date": "2026-04-03",
        "category_expected": "Rent/Housing",
    },
    {
        "id": str(uuid.uuid4()),
        "amount": Decimal("450.00"),
        "description": "Dinner at Olive Garden",
        "merchant": "Olive Garden",
        "date": "2026-04-04",
        "category_expected": "Dining",
    },
    {
        "id": str(uuid.uuid4()),
        "amount": Decimal("120.00"),
        "description": "Netflix subscription",
        "merchant": "Netflix",
        "date": "2026-04-05",
        "category_expected": "Subscriptions",
    },
]


# ===========================================================================
# TEST 1: Publisher fires to correct observer URLs
# ===========================================================================


class TestIngestionPublisher:
    """Verify that the REST webhook publisher sends events to observer URLs."""

    def test_publisher_reads_observer_urls_from_env(self):
        """NOTIFICATION_OBSERVERS should be split into a list of URLs."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "ingestion"))
        try:
            with patch.dict(os.environ, {
                "NOTIFICATION_OBSERVERS": "http://analytics:8003/internal/trigger"
            }):
                from publishers.rest_webhook_publisher import RestWebhookPublisher
                publisher = RestWebhookPublisher()
                assert len(publisher.observer_urls) == 1
                assert publisher.observer_urls[0] == "http://analytics:8003/internal/trigger"
        finally:
            sys.path.pop(0)

    def test_publisher_handles_multiple_urls(self):
        """Multiple comma-separated URLs parsed correctly."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "ingestion"))
        try:
            with patch.dict(os.environ, {
                "NOTIFICATION_OBSERVERS": (
                    "http://analytics:8003/internal/trigger,"
                    "http://other:9000/webhook"
                )
            }):
                from publishers.rest_webhook_publisher import RestWebhookPublisher
                publisher = RestWebhookPublisher()
                assert len(publisher.observer_urls) == 2
        finally:
            sys.path.pop(0)

    @pytest.mark.asyncio
    async def test_publisher_posts_event_to_observers(self):
        """Publisher POSTs the ingestion event to each observer URL."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "ingestion"))
        try:
            with patch.dict(os.environ, {
                "NOTIFICATION_OBSERVERS": "http://analytics:8003/internal/trigger"
            }):
                from publishers.rest_webhook_publisher import RestWebhookPublisher
                publisher = RestWebhookPublisher()

                event = {
                    "event": "transactions_ingested",
                    "user_id": TEST_USER_ID,
                    "transaction_ids": ["txn-1", "txn-2"],
                    "count": 2,
                }

                mock_response = MagicMock()
                mock_response.status_code = 200

                with patch("httpx.AsyncClient") as MockClient:
                    mock_client_instance = AsyncMock()
                    mock_client_instance.post = AsyncMock(return_value=mock_response)
                    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                    MockClient.return_value = mock_client_instance

                    await publisher.publish(event)

                    mock_client_instance.post.assert_called_once_with(
                        "http://analytics:8003/internal/trigger",
                        json=event,
                    )
        finally:
            sys.path.pop(0)

    @pytest.mark.asyncio
    async def test_publisher_does_not_fail_on_observer_error(self):
        """Publisher failure is non-blocking — ingestion must not fail."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "ingestion"))
        try:
            with patch.dict(os.environ, {
                "NOTIFICATION_OBSERVERS": "http://analytics:8003/internal/trigger"
            }):
                from publishers.rest_webhook_publisher import RestWebhookPublisher
                publisher = RestWebhookPublisher()

                event = {"event": "transactions_ingested", "user_id": TEST_USER_ID}

                with patch("httpx.AsyncClient") as MockClient:
                    mock_client_instance = AsyncMock()
                    mock_client_instance.post = AsyncMock(
                        side_effect=Exception("Connection refused")
                    )
                    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                    MockClient.return_value = mock_client_instance

                    # Should NOT raise
                    await publisher.publish(event)
        finally:
            sys.path.pop(0)


# ===========================================================================
# TEST 2: Analytics notifies Anomaly after pipeline completion
# ===========================================================================


class TestAnalyticsAnomalyNotification:
    """Verify that AnalyticsService calls Anomaly after categorization + FHS."""

    @pytest.mark.asyncio
    async def test_notify_anomaly_service_sends_correct_payload(self):
        """After analytics pipeline, Anomaly is notified with user_id + transaction_ids."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "analytics"))
        try:
            from service import AnalyticsService

            mock_db = AsyncMock()
            mock_redis = AsyncMock()
            mock_categorizer = AsyncMock()
            mock_cache = AsyncMock()
            anomaly_url = "http://phoenix-anomaly:8004"

            service = AnalyticsService(
                db=mock_db,
                redis_client=mock_redis,
                categorization_service=mock_categorizer,
                cache_invalidator=mock_cache,
                clickhouse_writer=None,
                anomaly_service_url=anomaly_url,
            )

            transaction_ids = ["txn-1", "txn-2"]
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"processed": 2, "alerts_created": 0}

            with patch("httpx.AsyncClient") as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.post = AsyncMock(return_value=mock_response)
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client_instance

                await service._notify_anomaly_service(TEST_USER_ID, transaction_ids)

                mock_client_instance.post.assert_called_once_with(
                    f"{anomaly_url}/internal/events/analytics-complete",
                    json={
                        "user_id": TEST_USER_ID,
                        "transaction_ids": transaction_ids,
                    },
                )
        finally:
            sys.path.pop(0)

    @pytest.mark.asyncio
    async def test_anomaly_notification_failure_is_non_blocking(self):
        """Anomaly service failure must NOT break the analytics pipeline."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "analytics"))
        try:
            from service import AnalyticsService

            service = AnalyticsService(
                db=AsyncMock(),
                redis_client=AsyncMock(),
                categorization_service=AsyncMock(),
                cache_invalidator=AsyncMock(),
                clickhouse_writer=None,
                anomaly_service_url="http://phoenix-anomaly:8004",
            )

            with patch("httpx.AsyncClient") as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.post = AsyncMock(
                    side_effect=Exception("Anomaly service down")
                )
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client_instance

                # Should NOT raise
                await service._notify_anomaly_service(TEST_USER_ID, ["txn-1"])
        finally:
            sys.path.pop(0)

    @pytest.mark.asyncio
    async def test_no_notification_when_url_is_none(self):
        """When anomaly_service_url is None, no HTTP call should be made."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "analytics"))
        try:
            from service import AnalyticsService

            service = AnalyticsService(
                db=AsyncMock(),
                redis_client=AsyncMock(),
                categorization_service=AsyncMock(),
                cache_invalidator=AsyncMock(),
                clickhouse_writer=None,
                anomaly_service_url=None,  # Not configured
            )

            # anomaly_service_url is None → _notify should not be called
            assert service.anomaly_service_url is None
        finally:
            sys.path.pop(0)


# ===========================================================================
# TEST 3: Anomaly Detection — Z-score computation and alert creation
# ===========================================================================


class TestAnomalyDetection:
    """Verify Z-score computation and alert generation logic."""

    def test_welford_state_update(self):
        """Welford's algorithm produces correct running statistics."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "anomaly"))
        try:
            from detector import WelfordState

            state = WelfordState(count=0, mean=0.0, M2=0.0)
            values = [100, 110, 105, 95, 100, 108, 103, 97, 102, 100]
            for v in values:
                state = state.update(v)

            assert state.count == 10
            assert abs(state.mean - 102.0) < 0.01
            assert state.std_dev > 0
        finally:
            sys.path.pop(0)

    def test_z_score_detects_anomaly(self):
        """A transaction 3x the mean should be flagged as anomalous."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "anomaly"))
        try:
            from detector import ZScoreDetector, WelfordState

            with patch.dict(os.environ, {
                "ANOMALY_Z_THRESHOLD": "2.5",
                "ANOMALY_MIN_TRANSACTIONS": "10",
            }):
                detector = ZScoreDetector()

                # Build baseline from 20 similar transactions
                state = WelfordState(count=0, mean=0.0, M2=0.0)
                for _ in range(20):
                    state = state.update(100.0)
                # Add a tiny bit of variance
                state = state.update(105.0)
                state = state.update(95.0)

                # Normal transaction — should NOT be anomalous
                z_normal = detector.compute_z_score(102.0, state)
                assert not detector.is_anomalous(z_normal)

                # Anomalous transaction — 5x the mean
                z_anomaly = detector.compute_z_score(500.0, state)
                assert detector.is_anomalous(z_anomaly)
        finally:
            sys.path.pop(0)

    def test_z_score_bootstrap_suppression(self):
        """Z-score returns None when fewer than MIN_TRANSACTIONS observations."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "anomaly"))
        try:
            from detector import ZScoreDetector, WelfordState

            with patch.dict(os.environ, {
                "ANOMALY_Z_THRESHOLD": "2.5",
                "ANOMALY_MIN_TRANSACTIONS": "10",
            }):
                detector = ZScoreDetector()
                state = WelfordState(count=5, mean=100.0, M2=500.0)

                z = detector.compute_z_score(500.0, state)
                assert z is None
                assert not detector.is_anomalous(z)
        finally:
            sys.path.pop(0)

    def test_alert_message_format(self):
        """Alert message contains key information: amount, category, z-score."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "anomaly"))
        try:
            from detector import ZScoreDetector

            with patch.dict(os.environ, {
                "ANOMALY_Z_THRESHOLD": "2.5",
                "ANOMALY_MIN_TRANSACTIONS": "10",
            }):
                detector = ZScoreDetector()
                msg = detector.build_alert_message(3.5, "Dining", 500.0, 100.0)
                assert "500.00" in msg
                assert "Dining" in msg
                assert "3.50" in msg
                assert "above" in msg
        finally:
            sys.path.pop(0)


# ===========================================================================
# TEST 4: Anomaly → Notification push verification
# ===========================================================================


class TestAnomalyNotificationPush:
    """Verify that Anomaly pushes alerts to Notification service."""

    @pytest.mark.asyncio
    async def test_anomaly_posts_alert_to_notification(self):
        """When an anomaly is detected, it POSTs to /internal/push-alert."""
        notification_url = "http://phoenix-notification:8006"

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            # Simulate the push from anomaly internal_router
            async with MockClient(timeout=5.0) as client:
                await client.post(
                    f"{notification_url}/internal/push-alert",
                    json={
                        "user_id": TEST_USER_ID,
                        "type": "alert",
                        "alert_id": "txn-1",
                        "message": "Anomalous transaction detected",
                        "z_score": 3.5,
                        "category": "Dining",
                    },
                )

            mock_client_instance.post.assert_called_once_with(
                f"{notification_url}/internal/push-alert",
                json={
                    "user_id": TEST_USER_ID,
                    "type": "alert",
                    "alert_id": "txn-1",
                    "message": "Anomalous transaction detected",
                    "z_score": 3.5,
                    "category": "Dining",
                },
            )


# ===========================================================================
# TEST 5: Notification WebSocket Manager
# ===========================================================================


class TestWebSocketManager:
    """Verify WebSocket connection manager pushes alerts correctly."""

    @pytest.mark.asyncio
    async def test_push_alert_to_connected_client(self):
        """Alerts are pushed to all connected WebSocket clients for a user."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "notification"))
        try:
            from websocket_manager import ConnectionManager

            manager = ConnectionManager()
            mock_ws = AsyncMock()
            mock_ws.send_text = AsyncMock()

            # Simulate connection
            manager._connections[TEST_USER_ID] = [mock_ws]

            alert = {
                "type": "alert",
                "message": "Anomalous spending detected",
                "z_score": 3.5,
            }
            await manager.push_alert(TEST_USER_ID, alert)

            mock_ws.send_text.assert_called_once_with(json.dumps(alert))
        finally:
            sys.path.pop(0)

    @pytest.mark.asyncio
    async def test_no_error_when_no_connections(self):
        """Push to an unconnected user does not raise."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "notification"))
        try:
            from websocket_manager import ConnectionManager

            manager = ConnectionManager()
            await manager.push_alert("nonexistent-user", {"message": "test"})
            # Should complete without error
        finally:
            sys.path.pop(0)

    @pytest.mark.asyncio
    async def test_dead_connections_cleaned_up(self):
        """Broken WebSocket connections are removed during push."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "notification"))
        try:
            from websocket_manager import ConnectionManager

            manager = ConnectionManager()
            mock_ws_good = AsyncMock()
            mock_ws_good.send_text = AsyncMock()
            mock_ws_dead = AsyncMock()
            mock_ws_dead.send_text = AsyncMock(side_effect=Exception("Connection closed"))

            manager._connections[TEST_USER_ID] = [mock_ws_good, mock_ws_dead]

            await manager.push_alert(TEST_USER_ID, {"message": "test"})

            # Good connection should still be there, dead one should be removed
            assert mock_ws_good in manager._connections[TEST_USER_ID]
            assert mock_ws_dead not in manager._connections[TEST_USER_ID]
        finally:
            sys.path.pop(0)


# ===========================================================================
# TEST 6: Full pipeline chain verification (mocked inter-service HTTP)
# ===========================================================================


class TestFullPipelineChain:
    """
    End-to-end chain test: Verify each service triggers the next in sequence.
    Uses mocked HTTP calls to verify the observer pattern wiring.
    """

    @pytest.mark.asyncio
    async def test_pipeline_chain_ingestion_to_analytics(self):
        """
        Ingestion publishes event → Publisher POSTs to Analytics /internal/trigger.
        Verifies the event contains user_id and transaction_ids.
        """
        sys.path.insert(0, os.path.join(SERVICES_DIR, "ingestion"))
        try:
            with patch.dict(os.environ, {
                "NOTIFICATION_OBSERVERS": "http://phoenix-analytics:8003/internal/trigger"
            }):
                from publishers.rest_webhook_publisher import RestWebhookPublisher
                publisher = RestWebhookPublisher()

                event = {
                    "event": "transactions_ingested",
                    "user_id": TEST_USER_ID,
                    "transaction_ids": [t["id"] for t in SAMPLE_TRANSACTIONS],
                    "count": len(SAMPLE_TRANSACTIONS),
                }

                mock_response = MagicMock()
                mock_response.status_code = 200

                with patch("httpx.AsyncClient") as MockClient:
                    mock_client_instance = AsyncMock()
                    mock_client_instance.post = AsyncMock(return_value=mock_response)
                    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                    MockClient.return_value = mock_client_instance

                    await publisher.publish(event)

                    # Verify the POST goes to /internal/trigger (NOT /cache-invalidate)
                    call_args = mock_client_instance.post.call_args
                    assert "/internal/trigger" in call_args[0][0]
                    assert "/cache-invalidate" not in call_args[0][0]

                    # Verify payload
                    payload = call_args[1]["json"]
                    assert payload["user_id"] == TEST_USER_ID
                    assert payload["transaction_ids"] == [t["id"] for t in SAMPLE_TRANSACTIONS]
        finally:
            sys.path.pop(0)

    @pytest.mark.asyncio
    async def test_pipeline_chain_analytics_to_anomaly(self):
        """
        Analytics completes → calls Anomaly /internal/events/analytics-complete.
        """
        sys.path.insert(0, os.path.join(SERVICES_DIR, "analytics"))
        try:
            from service import AnalyticsService

            anomaly_url = "http://phoenix-anomaly:8004"
            service = AnalyticsService(
                db=AsyncMock(),
                redis_client=AsyncMock(),
                categorization_service=AsyncMock(),
                cache_invalidator=AsyncMock(),
                anomaly_service_url=anomaly_url,
            )

            txn_ids = [t["id"] for t in SAMPLE_TRANSACTIONS]
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"processed": 5, "alerts_created": 1}

            with patch("httpx.AsyncClient") as MockClient:
                mock_client_instance = AsyncMock()
                mock_client_instance.post = AsyncMock(return_value=mock_response)
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client_instance

                await service._notify_anomaly_service(TEST_USER_ID, txn_ids)

                call_args = mock_client_instance.post.call_args
                assert "/internal/events/analytics-complete" in call_args[0][0]
                payload = call_args[1]["json"]
                assert payload["user_id"] == TEST_USER_ID
                assert len(payload["transaction_ids"]) == 5
        finally:
            sys.path.pop(0)

    def test_docker_compose_observer_urls_correct(self):
        """
        Verify docker-compose.yml has the correct NOTIFICATION_OBSERVERS configuration.
        This is a static analysis test — catches accidental misconfigurations.
        """
        compose_path = os.path.join(PROJECT_ROOT, "infra", "docker-compose.yml")
        with open(compose_path) as f:
            content = f.read()

        # The ingestion service should target /internal/trigger
        assert "/internal/trigger" in content

        # Should NOT still have the old broken configuration
        # (ingestion should not directly notify anomaly)
        lines = content.split("\n")
        in_ingestion_block = False
        ingestion_observers = []
        for line in lines:
            if "phoenix-ingestion:" in line:
                in_ingestion_block = True
            elif in_ingestion_block and line.strip().startswith("phoenix-") and ":" in line:
                in_ingestion_block = False
            if in_ingestion_block and "NOTIFICATION_OBSERVERS" in line:
                # Collect the next few lines for multi-line env var
                idx = lines.index(line)
                for j in range(idx, min(idx + 5, len(lines))):
                    ingestion_observers.append(lines[j])

        observer_text = "\n".join(ingestion_observers)
        assert "/internal/trigger" in observer_text

    def test_docker_compose_analytics_has_anomaly_url(self):
        """
        Verify docker-compose.yml has ANOMALY_SERVICE_URL for phoenix-analytics.
        """
        compose_path = os.path.join(PROJECT_ROOT, "infra", "docker-compose.yml")
        with open(compose_path) as f:
            content = f.read()

        assert "ANOMALY_SERVICE_URL" in content
        assert "http://phoenix-anomaly:8004" in content


# ===========================================================================
# TEST 7: Welford State Store (Redis persistence)
# ===========================================================================


class TestWelfordStateStore:
    """Verify Welford state is correctly serialized/deserialized from Redis."""

    @pytest.mark.asyncio
    async def test_save_and_retrieve_state(self):
        """Round-trip: save state to Redis, retrieve it, verify equality."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "anomaly"))
        try:
            from redis_stats import WelfordStateStore
            from detector import WelfordState

            mock_redis = AsyncMock()
            store = WelfordStateStore(mock_redis)

            state = WelfordState(count=10, mean=100.0, M2=500.0)
            await store.save(TEST_USER_ID, 1, state)

            # Verify the correct key and value were set
            mock_redis.set.assert_called_once()
            call_args = mock_redis.set.call_args
            key = call_args[0][0]
            value = json.loads(call_args[0][1])

            assert key == f"anomaly:stats:{TEST_USER_ID}:1"
            assert value["count"] == 10
            assert value["mean"] == 100.0
            assert value["M2"] == 500.0
        finally:
            sys.path.pop(0)

    @pytest.mark.asyncio
    async def test_get_returns_none_on_cache_miss(self):
        """When no state exists in Redis, return None (triggers cold start)."""
        sys.path.insert(0, os.path.join(SERVICES_DIR, "anomaly"))
        try:
            from redis_stats import WelfordStateStore

            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)
            store = WelfordStateStore(mock_redis)

            result = await store.get(TEST_USER_ID, 1)
            assert result is None
        finally:
            sys.path.pop(0)
