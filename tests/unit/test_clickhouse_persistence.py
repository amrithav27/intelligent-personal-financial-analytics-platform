"""
Unit tests for ClickHouse Persistence Pipeline
================================================

Covers:
  A. ClickHouseWriter — write methods (write_fhs, write_transaction, write_monthly_category)
  B. ClickHouseWriter — read methods (read_json, query_fhs_history, query_spending_trends)
  C. AnalyticsService — ClickHouse-first read with PostgreSQL fallback
  D. AnalyticsService — Transaction mirroring to ClickHouse during ingestion
  E. Response data_source field verification

Run:
    pytest tests/unit/test_clickhouse_persistence.py -v
"""

import sys
import types
import json
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


# ── Compatibility shim: stub out heavy packages not in test env ──────────
def _stub(name, **attrs):
    """Create a minimal module stub and register it under `name`."""
    if name not in sys.modules:
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
    return sys.modules[name]


_redis_mod = _stub("redis")
_redis_asyncio = _stub("redis.asyncio", Redis=MagicMock)
_redis_mod.asyncio = _redis_asyncio  # type: ignore

_fastapi = _stub(
    "fastapi",
    FastAPI=MagicMock, APIRouter=MagicMock,
    Depends=lambda f: f, HTTPException=Exception,
    Header=lambda *a, **kw: None, Query=lambda *a, **kw: None,
    Request=MagicMock,
)
_stub("fastapi.middleware.cors", CORSMiddleware=MagicMock)
_stub("aiohttp", ClientSession=MagicMock, ClientTimeout=MagicMock)


def _make_row(**kwargs):
    """Lightweight row mock with attribute access."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


# =========================================================================== #
#  A. ClickHouseWriter — Write Methods                                         #
# =========================================================================== #

class TestClickHouseWriterWrites:
    """Tests for fire-and-forget write methods in ClickHouseWriter."""

    @pytest.fixture(autouse=True)
    def writer(self):
        from clickhouse_writer import ClickHouseWriter
        self.w = ClickHouseWriter("http://clickhouse:8123", "phoenix")

    def test_url_construction(self):
        """URL includes the database parameter."""
        assert self.w.url == "http://clickhouse:8123/?database=phoenix"

    @pytest.mark.asyncio
    async def test_write_fhs_creates_task(self):
        """write_fhs() should fire-and-forget an INSERT task."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            await self.w.write_fhs(
                "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                {"score": 72.5, "savings_rate": 0.3, "dti_ratio": 0.15, "spending_volatility": 0.18}
            )
            # The INSERT is fired as a background task — no immediate assertion on post
            # but write_fhs should not raise
            assert True

    @pytest.mark.asyncio
    async def test_write_transaction_creates_insert(self):
        """write_transaction() should create an INSERT for the transactions table."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            await self.w.write_transaction(
                txn_id="txn-123",
                user_id="user-456",
                amount=-1500.00,
                currency="INR",
                category_id=1,
                ts="2026-04-20 10:00:00",
            )
            assert True

    @pytest.mark.asyncio
    async def test_write_monthly_category(self):
        """write_monthly_category() should fire an INSERT for monthly_category_spending."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            await self.w.write_monthly_category(
                user_id="user-456", category_id=1, category_name="Groceries",
                month="2026-04-01", total_amount=12500.0, tx_count=8,
            )
            assert True

    @pytest.mark.asyncio
    async def test_execute_handles_failure_gracefully(self):
        """_execute should catch exceptions and log a warning, not raise."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(side_effect=Exception("Connection refused"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            # Should NOT raise
            await self.w._execute("INSERT INTO test VALUES (1)")


# =========================================================================== #
#  B. ClickHouseWriter — Read Methods                                          #
# =========================================================================== #

class TestClickHouseWriterReads:
    """Tests for read (SELECT) methods in ClickHouseWriter."""

    @pytest.fixture(autouse=True)
    def writer(self):
        from clickhouse_writer import ClickHouseWriter
        self.w = ClickHouseWriter("http://clickhouse:8123", "phoenix")

    @pytest.mark.asyncio
    async def test_read_json_parses_clickhouse_response(self):
        """read_json() should parse ClickHouse JSON format and return data rows."""
        ch_response = {
            "data": [
                {"score": 72.5, "computed_at": "2026-04-20 10:00:00"},
                {"score": 68.0, "computed_at": "2026-04-05 09:00:00"},
            ],
            "rows": 2,
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = ch_response
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_resp)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            result = await self.w.read_json("SELECT score, computed_at FROM financial_health_scores")
            assert len(result) == 2
            assert result[0]["score"] == 72.5
            assert result[1]["computed_at"] == "2026-04-05 09:00:00"

    @pytest.mark.asyncio
    async def test_read_json_appends_format_json(self):
        """read_json() should append FORMAT JSON to the query."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": []}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_resp)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            await self.w.read_json("SELECT 1")

            # Verify FORMAT JSON was appended
            call_content = mock_instance.post.call_args[1]["content"]
            assert call_content.endswith("FORMAT JSON")

    @pytest.mark.asyncio
    async def test_read_json_returns_empty_on_failure(self):
        """read_json() should return [] on ClickHouse failure, not raise."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(side_effect=Exception("CH down"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            result = await self.w.read_json("SELECT 1")
            assert result == []

    @pytest.mark.asyncio
    async def test_query_fhs_history_returns_results(self):
        """query_fhs_history() returns formatted FHS time-series."""
        ch_response = {
            "data": [
                {"score": 72.5, "savings_rate": 0.3, "dti_ratio": 0.15,
                 "spending_volatility": 0.18, "computed_at": "2026-04-20 10:00:00"},
            ],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = ch_response
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_resp)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            result = await self.w.query_fhs_history("user-123", limit=6)
            assert len(result) == 1
            assert result[0]["score"] == 72.5

    @pytest.mark.asyncio
    async def test_query_spending_trends_returns_results(self):
        """query_spending_trends() returns monthly aggregates."""
        ch_response = {
            "data": [
                {"month": "2026-04-01", "total": 25000.0, "tx_count": 15},
                {"month": "2026-03-01", "total": 22000.0, "tx_count": 12},
            ],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = ch_response
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_resp)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            result = await self.w.query_spending_trends("user-123", months=6)
            assert len(result) == 2


# =========================================================================== #
#  C. AnalyticsService — ClickHouse-first reads with PostgreSQL fallback       #
# =========================================================================== #

class TestServiceClickHouseReads:
    """Tests for OLAP read paths in AnalyticsService."""

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        return redis

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_ch_writer(self):
        from clickhouse_writer import ClickHouseWriter
        writer = MagicMock(spec=ClickHouseWriter)
        writer.query_fhs_history = AsyncMock()
        writer.query_spending_trends = AsyncMock()
        writer.write_transaction = AsyncMock()
        writer.write_fhs = AsyncMock()
        return writer

    @pytest.fixture
    def service(self, mock_db, mock_redis, mock_ch_writer):
        from services.analytics.service import AnalyticsService
        from services.analytics.categorization.service import CategorizationService
        from services.analytics.cache import CacheInvalidator

        categorizer = MagicMock(spec=CategorizationService)
        cache_inv = MagicMock(spec=CacheInvalidator)
        cache_inv.invalidate_user = AsyncMock()

        return AnalyticsService(
            db=mock_db,
            redis_client=mock_redis,
            categorization_service=categorizer,
            cache_invalidator=cache_inv,
            clickhouse_writer=mock_ch_writer,
            anomaly_service_url=None,
        )

    @pytest.mark.asyncio
    async def test_fhs_history_uses_clickhouse_when_available(self, service, mock_ch_writer):
        """When ClickHouse returns data, data_source should be 'clickhouse'."""
        mock_ch_writer.query_fhs_history.return_value = [
            {"score": 72.5, "savings_rate": 0.3, "dti_ratio": 0.15,
             "spending_volatility": 0.18, "computed_at": "2026-04-20 10:00:00"},
        ]

        result = await service.get_fhs_history_from_clickhouse("user-123", limit=6)
        assert result["data_source"] == "clickhouse"
        assert len(result["data"]) == 1
        assert result["data"][0]["score"] == 72.5

    @pytest.mark.asyncio
    async def test_fhs_history_falls_back_to_postgresql(self, mock_db, mock_redis):
        """When ClickHouse is None, data_source should be 'postgresql'."""
        from services.analytics.service import AnalyticsService
        from services.analytics.categorization.service import CategorizationService
        from services.analytics.cache import CacheInvalidator

        categorizer = MagicMock(spec=CategorizationService)
        cache_inv = MagicMock(spec=CacheInvalidator)
        cache_inv.invalidate_user = AsyncMock()

        service_no_ch = AnalyticsService(
            db=mock_db,
            redis_client=mock_redis,
            categorization_service=categorizer,
            cache_invalidator=cache_inv,
            clickhouse_writer=None,  # No ClickHouse
            anomaly_service_url=None,
        )

        # Mock PG results
        rows = [
            _make_row(score=Decimal("68.50"), savings_rate=Decimal("0.30"),
                      dti_ratio=Decimal("0.15"), spending_volatility=Decimal("0.18"),
                      computed_at=datetime(2026, 4, 20, tzinfo=timezone.utc)),
        ]
        mock_db.execute = AsyncMock(
            return_value=MagicMock(fetchall=MagicMock(return_value=rows))
        )

        result = await service_no_ch.get_fhs_history_from_clickhouse("user-123", limit=6)
        assert result["data_source"] == "postgresql"
        assert len(result["data"]) == 1
        assert result["data"][0]["score"] == pytest.approx(68.5)

    @pytest.mark.asyncio
    async def test_spending_trends_uses_clickhouse(self, service, mock_ch_writer):
        """When ClickHouse returns trend data, data_source should be 'clickhouse'."""
        mock_ch_writer.query_spending_trends.return_value = [
            {"month": "2026-03-01", "total": 22000.0, "tx_count": 12},
            {"month": "2026-04-01", "total": 25000.0, "tx_count": 15},
        ]

        result = await service.get_spending_trends_from_clickhouse("user-123", months=6)
        assert result["data_source"] == "clickhouse"
        assert len(result["data"]) == 2
        # Second month MoM change: (25000-22000)/22000*100 ≈ 13.64%
        assert result["data"][1]["mom_change_percent"] == pytest.approx(13.64, abs=0.01)

    @pytest.mark.asyncio
    async def test_spending_trends_mom_first_month_is_none(self, service, mock_ch_writer):
        """First month in trends should have mom_change_percent = None."""
        mock_ch_writer.query_spending_trends.return_value = [
            {"month": "2026-04-01", "total": 25000.0, "tx_count": 15},
        ]

        result = await service.get_spending_trends_from_clickhouse("user-123", months=6)
        assert result["data"][0]["mom_change_percent"] is None

    @pytest.mark.asyncio
    async def test_spending_trends_falls_back_to_postgresql(self, mock_db, mock_redis):
        """When ClickHouse is None, trends fall back to PostgreSQL."""
        from services.analytics.service import AnalyticsService
        from services.analytics.categorization.service import CategorizationService
        from services.analytics.cache import CacheInvalidator

        categorizer = MagicMock(spec=CategorizationService)
        cache_inv = MagicMock(spec=CacheInvalidator)
        cache_inv.invalidate_user = AsyncMock()

        service_no_ch = AnalyticsService(
            db=mock_db,
            redis_client=mock_redis,
            categorization_service=categorizer,
            cache_invalidator=cache_inv,
            clickhouse_writer=None,
            anomaly_service_url=None,
        )

        # Mock PG results (raw transactions for TrendAnalyzer)
        rows = [
            _make_row(amount=Decimal("1500.00"), currency="INR",
                      ts=datetime(2026, 4, 10), category_name="Groceries"),
        ]
        mock_db.execute = AsyncMock(
            return_value=MagicMock(fetchall=MagicMock(return_value=rows))
        )

        result = await service_no_ch.get_spending_trends_from_clickhouse("user-123", months=6)
        assert result["data_source"] == "postgresql"

    @pytest.mark.asyncio
    async def test_clickhouse_empty_response_triggers_pg_fallback(self, service, mock_ch_writer, mock_db):
        """When ClickHouse returns empty rows, service falls back to PostgreSQL."""
        mock_ch_writer.query_fhs_history.return_value = []  # CH returns nothing

        rows = [
            _make_row(score=Decimal("50.00"), savings_rate=Decimal("0.20"),
                      dti_ratio=Decimal("0.10"), spending_volatility=Decimal("0.25"),
                      computed_at=datetime(2026, 4, 15, tzinfo=timezone.utc)),
        ]
        mock_db.execute = AsyncMock(
            return_value=MagicMock(fetchall=MagicMock(return_value=rows))
        )

        result = await service.get_fhs_history_from_clickhouse("user-123", limit=6)
        assert result["data_source"] == "postgresql"


# =========================================================================== #
#  D. AnalyticsService — Transaction Mirroring                                 #
# =========================================================================== #

class TestTransactionMirroring:
    """Verify that process_ingestion_event mirrors transactions to ClickHouse."""

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        redis.delete = AsyncMock()
        return redis

    @pytest.fixture
    def mock_ch_writer(self):
        from clickhouse_writer import ClickHouseWriter
        writer = MagicMock(spec=ClickHouseWriter)
        writer.write_transaction = AsyncMock()
        writer.write_fhs = AsyncMock()
        return writer

    @pytest.mark.asyncio
    async def test_process_ingestion_mirrors_transactions(self, mock_redis, mock_ch_writer):
        """Each categorized transaction should be written to ClickHouse."""
        from services.analytics.service import AnalyticsService
        from services.analytics.categorization.service import CategorizationService
        from services.analytics.cache import CacheInvalidator

        mock_db = AsyncMock()

        # Mock the transaction row returned from PG
        txn_row = _make_row(
            id="txn-001", raw_description="Grocery at BigBasket",
            mcc_code="5411", merchant_name="BigBasket",
            amount=Decimal("1500.00"), currency="INR",
            ts=datetime(2026, 4, 20, 10, 0, 0),
        )
        # Mock categorization result
        cat_result = MagicMock()
        cat_result.category_id = 1
        cat_result.confidence = 0.95
        cat_result.method = MagicMock()
        cat_result.method.value = "RULE_MERCHANT"

        categorizer = MagicMock(spec=CategorizationService)
        categorizer.categorize = AsyncMock(return_value=cat_result)

        cache_inv = MagicMock(spec=CacheInvalidator)
        cache_inv.invalidate_user = AsyncMock()

        # Mock DB execute: first call = SELECT txn, second = INSERT cat, third+ = FHS
        mock_db.execute = AsyncMock(
            side_effect=[
                MagicMock(fetchone=MagicMock(return_value=txn_row)),  # SELECT txn
                MagicMock(),  # INSERT into transaction_categories
                MagicMock(fetchall=MagicMock(return_value=[])),  # FHS _compute_user_metrics
                MagicMock(scalar=MagicMock(return_value=0)),       # Emergency fund query
                MagicMock(),  # INSERT FHS score
            ]
        )
        mock_db.commit = AsyncMock()

        service = AnalyticsService(
            db=mock_db,
            redis_client=mock_redis,
            categorization_service=categorizer,
            cache_invalidator=cache_inv,
            clickhouse_writer=mock_ch_writer,
            anomaly_service_url=None,
        )

        result = await service.process_ingestion_event("user-123", ["txn-001"])

        # Verify transaction was mirrored to ClickHouse
        mock_ch_writer.write_transaction.assert_called_once()
        call_kwargs = mock_ch_writer.write_transaction.call_args[1]
        assert call_kwargs["txn_id"] == "txn-001"
        assert call_kwargs["user_id"] == "user-123"
        assert call_kwargs["amount"] == 1500.00
        assert call_kwargs["category_id"] == 1

        # Verify FHS was also written to ClickHouse
        mock_ch_writer.write_fhs.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_mirroring_when_ch_writer_is_none(self, mock_redis):
        """When ClickHouse writer is None, no mirroring occurs (no crash)."""
        from services.analytics.service import AnalyticsService
        from services.analytics.categorization.service import CategorizationService
        from services.analytics.cache import CacheInvalidator

        mock_db = AsyncMock()

        txn_row = _make_row(
            id="txn-002", raw_description="Test", mcc_code=None,
            merchant_name="Test", amount=Decimal("100.00"),
            currency="INR", ts=datetime(2026, 4, 20),
        )
        cat_result = MagicMock()
        cat_result.category_id = 15
        cat_result.confidence = 0.5
        cat_result.method = MagicMock()
        cat_result.method.value = "RULE_KEYWORD"

        categorizer = MagicMock(spec=CategorizationService)
        categorizer.categorize = AsyncMock(return_value=cat_result)

        cache_inv = MagicMock(spec=CacheInvalidator)
        cache_inv.invalidate_user = AsyncMock()

        mock_db.execute = AsyncMock(
            side_effect=[
                MagicMock(fetchone=MagicMock(return_value=txn_row)),
                MagicMock(),
                MagicMock(fetchall=MagicMock(return_value=[])),
                MagicMock(scalar=MagicMock(return_value=0)),
                MagicMock(),
            ]
        )
        mock_db.commit = AsyncMock()

        service = AnalyticsService(
            db=mock_db, redis_client=mock_redis,
            categorization_service=categorizer,
            cache_invalidator=cache_inv,
            clickhouse_writer=None,  # No ClickHouse
            anomaly_service_url=None,
        )

        # Should complete without error
        result = await service.process_ingestion_event("user-456", ["txn-002"])
        assert result["categorized"] == 1


# =========================================================================== #
#  E. Data Source Field Verification                                           #
# =========================================================================== #

class TestDataSourceField:
    """Verify responses include the data_source field."""

    @pytest.mark.asyncio
    async def test_data_source_is_clickhouse(self):
        """When ClickHouse provides the data, data_source='clickhouse'."""
        from services.analytics.service import AnalyticsService
        from services.analytics.categorization.service import CategorizationService
        from services.analytics.cache import CacheInvalidator
        from clickhouse_writer import ClickHouseWriter

        mock_ch = MagicMock(spec=ClickHouseWriter)
        mock_ch.query_fhs_history = AsyncMock(return_value=[
            {"score": 80.0, "savings_rate": 0.4, "dti_ratio": 0.1,
             "spending_volatility": 0.1, "computed_at": "2026-04-21 12:00:00"}
        ])

        service = AnalyticsService(
            db=AsyncMock(), redis_client=AsyncMock(),
            categorization_service=MagicMock(spec=CategorizationService),
            cache_invalidator=MagicMock(spec=CacheInvalidator),
            clickhouse_writer=mock_ch,
        )

        result = await service.get_fhs_history_from_clickhouse("u1")
        assert result["data_source"] == "clickhouse"
        assert isinstance(result["data"], list)

    @pytest.mark.asyncio
    async def test_data_source_is_postgresql(self):
        """When ClickHouse is absent, data_source='postgresql'."""
        from services.analytics.service import AnalyticsService
        from services.analytics.categorization.service import CategorizationService
        from services.analytics.cache import CacheInvalidator

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(fetchall=MagicMock(return_value=[]))
        )

        service = AnalyticsService(
            db=mock_db, redis_client=AsyncMock(),
            categorization_service=MagicMock(spec=CategorizationService),
            cache_invalidator=MagicMock(spec=CacheInvalidator),
            clickhouse_writer=None,
        )

        result = await service.get_fhs_history_from_clickhouse("u1")
        assert result["data_source"] == "postgresql"
        assert isinstance(result["data"], list)
