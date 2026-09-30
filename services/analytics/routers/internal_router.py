"""Internal Router — endpoints called by other services (Observer webhook targets)."""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from service import AnalyticsService
from categorization.service import CategorizationService
from cache import CacheInvalidator
from clickhouse_writer import ClickHouseWriter
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal")


async def get_db():
    raise NotImplementedError("get_db must be overridden at app startup")

async def get_redis():
    raise NotImplementedError("get_redis must be overridden at app startup")


@router.post("/trigger")
async def trigger_analytics(
    event: dict,
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    """
    Observer webhook endpoint: called by Ingestion Service after new transactions are ingested.
    Triggers the full analytics pipeline (categorize → FHS → cache invalidation → ClickHouse).
    """
    user_id = event.get("user_id")
    transaction_ids = event.get("transaction_ids", [])

    if not user_id or not transaction_ids:
        return {"status": "skip", "reason": "No user_id or transaction_ids"}

    categorizer = CategorizationService(redis_client)
    cache_invalidator = CacheInvalidator(redis_client)
    ch_writer = None
    ch_url = os.getenv("CLICKHOUSE_URL")
    ch_db = os.getenv("CLICKHOUSE_DB", "phoenix")
    if ch_url:
        ch_writer = ClickHouseWriter(ch_url, ch_db)
    anomaly_url = os.getenv("ANOMALY_SERVICE_URL")

    service = AnalyticsService(db, redis_client, categorizer, cache_invalidator, ch_writer, anomaly_url)
    result = await service.process_ingestion_event(user_id, transaction_ids)

    logger.info(f"Analytics pipeline complete for user {user_id}: {result}")
    return {"status": "ok", **result}


@router.post("/cache-invalidate")
async def cache_invalidate(
    event: dict,
    redis_client: aioredis.Redis = Depends(get_redis),
):
    """
    Called by Ingestion Service to invalidate cache after ingestion.
    """
    user_id = event.get("user_id")
    if user_id:
        invalidator = CacheInvalidator(redis_client)
        await invalidator.invalidate_user(user_id)
    return {"status": "ok"}
