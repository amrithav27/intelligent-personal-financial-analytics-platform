"""WebSocket Connection Manager — manages active connections per user."""

import json
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections per user."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(user_id, []).append(websocket)
        logger.info(f"WebSocket connected for user {user_id}")

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        conns = self._connections.get(user_id, [])
        if websocket in conns:
            conns.remove(websocket)
        logger.info(f"WebSocket disconnected for user {user_id}")

    async def push_alert(self, user_id: str, alert: dict) -> None:
        """Push alert to all connected clients for this user."""
        conns = self._connections.get(user_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_text(json.dumps(alert))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    @property
    def active_connections(self) -> int:
        return sum(len(conns) for conns in self._connections.values())


manager = ConnectionManager()  # Module-level singleton
