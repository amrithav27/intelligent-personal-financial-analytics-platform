"""WebSocket Router — real-time alert delivery via WebSocket."""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import jwt, JWTError
import base64
import os

from websocket_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()


def validate_jwt_token(token: str) -> str:
    """Validate JWT token and return user_id."""
    try:
        public_key = base64.b64decode(os.environ.get("JWT_PUBLIC_KEY", ""))
        payload = jwt.decode(token, public_key, algorithms=["RS256"])
        return payload["sub"]
    except (JWTError, KeyError, Exception) as e:
        logger.warning(f"WebSocket JWT validation failed: {e}")
        raise ValueError("Invalid token")


@router.websocket("/ws/v1/alerts")
async def alert_websocket(websocket: WebSocket, token: str = Query(...)):
    """
    WebSocket endpoint for real-time alert delivery.
    JWT token passed as query parameter (WebSocket can't set Authorization header).
    """
    try:
        user_id = validate_jwt_token(token)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
