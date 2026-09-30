"""Anomaly Detection — public alert endpoints."""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(redirect_slashes=False)


async def get_db():
    raise NotImplementedError("get_db must be overridden at app startup")


@router.get("", response_model=None)
async def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """List anomaly alerts for the authenticated user with pagination and category metadata."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")
    logger.info(f"LIST_ALERTS: user_id={x_user_id}")

    offset = (page - 1) * page_size
    conditions: list[str] = ["a.user_id = :uid"]
    params: dict = {"uid": x_user_id}

    if unread_only:
        conditions.append("a.acknowledged_at IS NULL")

    where_clause = " AND ".join(conditions)

    # 1. Total count for pagination parity with transactions
    count_sql = f"SELECT COUNT(*) FROM anomaly_alerts a WHERE {where_clause}"
    count_result = await db.execute(text(count_sql), params)
    total = count_result.scalar() or 0

    # 2. Optimized fetch with category join (for better frontend rendering)
    fetch_sql = (
        "SELECT a.id, a.transaction_id, a.category_id, a.z_score, a.description, "
        "a.acknowledged_at, a.created_at, c.name AS category_name, c.icon AS category_icon "
        "FROM anomaly_alerts a "
        "LEFT JOIN categories c ON a.category_id = c.id "
        f"WHERE {where_clause} "
        "ORDER BY a.created_at DESC "
        "LIMIT :lim OFFSET :off"
    )
    params.update({"lim": page_size, "off": offset})
    
    result = await db.execute(text(fetch_sql), params)
    rows = result.fetchall()

    return {
        "alerts": [
            {
                "id": str(row.id),
                "transaction_id": str(row.transaction_id) if row.transaction_id else None,
                "category_id": row.category_id,
                "category_name": row.category_name,
                "category_icon": row.category_icon,
                "z_score": float(row.z_score),
                "description": row.description,
                "acknowledged_at": str(row.acknowledged_at) if row.acknowledged_at else None,
                "created_at": str(row.created_at),
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Mark an alert as acknowledged."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")

    await db.execute(
        text(
            "UPDATE anomaly_alerts SET acknowledged_at = NOW() "
            "WHERE id = :aid AND user_id = :uid AND acknowledged_at IS NULL"
        ),
        {"aid": alert_id, "uid": x_user_id},
    )
    await db.commit()
    return {"status": "acknowledged"}
