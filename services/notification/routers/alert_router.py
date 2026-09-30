"""Alert Router — internal endpoint for pushing alerts."""

import logging
from fastapi import APIRouter

from websocket_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/internal/push-alert")
async def push_alert(alert: dict):
    """
    Called by Anomaly Detection Service to push WebSocket alerts.
    """
    user_id = alert.get("user_id")
    if not user_id:
        return {"status": "error", "reason": "No user_id"}

    await manager.push_alert(user_id, alert)
    return {"status": "ok", "active_connections": manager.active_connections}


@router.get("/alerts/unread-count")
async def unread_count():
    """Get count of active WebSocket connections (monitoring)."""
    return {"active_connections": manager.active_connections}
