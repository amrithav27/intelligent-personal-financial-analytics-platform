"""Analytics Router — dashboard overview, FHS history, category distribution, trends."""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from service import AnalyticsService
from categorization.service import CategorizationService
from cache import CacheInvalidator
from clickhouse_writer import ClickHouseWriter
from processors.trend_analyzer import TrendAnalyzer

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_db():
    raise NotImplementedError("get_db must be overridden at app startup")


async def get_redis():
    raise NotImplementedError("get_redis must be overridden at app startup")


def _require_user_id(x_user_id: str = Header(None, alias="X-User-ID")) -> str:
    """Shared dependency: extracts and validates the X-User-ID header."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")
    return x_user_id


async def get_analytics_service(
    request: Request,
    user_id: str = Depends(_require_user_id),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> AnalyticsService:
    """
    Repository Pattern: Builds an AnalyticsService with a user-scoped DB session.

    Retrieves `get_db_for_user` factory from app.state (registered during lifespan)
    and creates a session that has `app.current_user_id` set for this request's user.
    This ensures RLS policies evaluate correctly for all queries inside the service.
    """
    import os
    get_db_for_user = request.app.state.get_db_for_user
    db_factory = get_db_for_user(user_id)

    # Collect the session from the async generator
    db_gen = db_factory()
    db: AsyncSession = await db_gen.__anext__()

    categorizer = CategorizationService(redis_client)
    cache_invalidator = CacheInvalidator(redis_client)
    ch_writer = None
    ch_url = os.getenv("CLICKHOUSE_URL")
    ch_db = os.getenv("CLICKHOUSE_DB", "phoenix")
    if ch_url:
        ch_writer = ClickHouseWriter(ch_url, ch_db)
    return AnalyticsService(db, redis_client, categorizer, cache_invalidator, ch_writer, anomaly_service_url=None)


@router.get("/dashboard/overview")
async def dashboard_overview(
    user_id: str = Depends(_require_user_id),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    FACADE PATTERN: Single endpoint aggregating FHS, categories,
    recent transactions, unread alerts, and budget status.

    RLS context (`app.current_user_id`) is set transparently by the
    `get_analytics_service` dependency via `get_db_for_user`.
    """
    return await service.get_dashboard_overview(user_id)


@router.get("/fhs/history")
async def fhs_history(
    request: Request,
    months: int = Query(6, ge=1, le=24),
    user_id: str = Depends(_require_user_id),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get FHS score history for the last N months.
    ADR-002: Routes to ClickHouse (OLAP) first, falls back to PostgreSQL (OLTP).
    Response includes 'data_source' to indicate which database served the query.
    """
    return await service.get_fhs_history_from_clickhouse(user_id, limit=months)


@router.get("/categories")
async def category_distribution(
    month: str = Query(None, description="YYYY-MM format"),
    user_id: str = Depends(_require_user_id),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Get spending distribution by category for a given month."""
    return await service._get_category_distribution(user_id)


@router.get("/trends")
async def spending_trends(
    request: Request,
    months: int = Query(6, ge=1, le=24),
    user_id: str = Depends(_require_user_id),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """
    Get monthly spending trends.
    ADR-002: Routes to ClickHouse (OLAP) first, falls back to PostgreSQL (OLTP).
    Response includes 'data_source' to indicate which database served the query.
    """
    return await service.get_spending_trends_from_clickhouse(user_id, months)
