"""Internal Router — Observer webhook endpoint for anomaly detection."""

import logging
import httpx
import os
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from detector import ZScoreDetector, WelfordState
from redis_stats import WelfordStateStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal")
detector = ZScoreDetector()


async def get_db():
    raise NotImplementedError("get_db must be overridden at app startup")

async def get_redis():
    raise NotImplementedError("get_redis must be overridden at app startup")


@router.post("/events/analytics-complete")
async def handle_analytics_complete(
    event: dict,
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    """
    OBSERVER PATTERN: This endpoint is the 'update()' method of the Observer interface.
    Called by Analytics Engine (Subject) after each computation cycle.
    """
    user_id = event.get("user_id")
    transaction_ids = event.get("transaction_ids", [])

    if not user_id or not transaction_ids:
        return {"status": "skip", "reason": "No user_id or transaction_ids"}

    # Load transactions with their categories from DB
    stats_store = WelfordStateStore(redis_client)
    alerts_created = []

    for txn_id in transaction_ids:
        result = await db.execute(
            text(
                "SELECT t.id, t.amount, t.merchant_name, "
                "tc.category_id, c.name as category_name "
                "FROM transactions t "
                "LEFT JOIN transaction_categories tc ON t.id = tc.transaction_id "
                "LEFT JOIN categories c ON tc.category_id = c.id "
                "WHERE t.id = :tid"
            ),
            {"tid": txn_id},
        )
        row = result.fetchone()
        if not row or not row.category_id:
            continue

        # Get current Welford state for this user+category
        state = await stats_store.get(user_id, row.category_id)
        if state is None:
            # Cold start: rebuild from last 30 days
            state = await _rebuild_state_from_db(db, user_id, row.category_id)

        # Compute Z-score
        amount = float(row.amount)
        z = detector.compute_z_score(amount, state)

        # Update Welford state
        new_state = state.update(amount)
        await stats_store.save(user_id, row.category_id, new_state)

        # Create alert if anomalous
        if detector.is_anomalous(z):
            msg = detector.build_alert_message(
                z, row.category_name or "Other", amount, state.mean
            )
            # Insert alert
            await db.execute(
                text(
                    "INSERT INTO anomaly_alerts "
                    "(user_id, transaction_id, category_id, z_score, description) "
                    "VALUES (:uid, :tid, :cid, :z, :desc)"
                ),
                {
                    "uid": user_id,
                    "tid": txn_id,
                    "cid": row.category_id,
                    "z": z,
                    "desc": msg,
                },
            )
            await db.commit()
            alerts_created.append({"transaction_id": txn_id, "z_score": z, "message": msg})

            # Notify Notification Service to push WebSocket alert
            notification_url = os.getenv("NOTIFICATION_SERVICE_URL", "http://phoenix-notification:8006")
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        f"{notification_url}/internal/push-alert",
                        json={
                            "user_id": user_id,
                            "type": "alert",
                            "alert_id": txn_id,
                            "message": msg,
                            "z_score": z,
                            "category": row.category_name,
                        },
                    )
            except Exception as e:
                logger.warning(f"Failed to push alert to notification service: {e}")

    return {"processed": len(transaction_ids), "alerts_created": len(alerts_created)}


async def _rebuild_state_from_db(
    db: AsyncSession, user_id: str, category_id: int
) -> WelfordState:
    """Rebuild Welford state from the last 30 days of transactions."""
    result = await db.execute(
        text(
            "SELECT t.amount FROM transactions t "
            "JOIN transaction_categories tc ON t.id = tc.transaction_id "
            "WHERE t.user_id = :uid AND tc.category_id = :cid "
            "AND t.ts >= CURRENT_DATE - INTERVAL '30 days' "
            "ORDER BY t.ts"
        ),
        {"uid": user_id, "cid": category_id},
    )
    state = WelfordState(count=0, mean=0.0, M2=0.0)
    for row in result.fetchall():
        state = state.update(float(row.amount))
    return state
