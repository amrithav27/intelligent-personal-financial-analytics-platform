"""Welford State Store — persists running stats in Redis."""

import json
import redis.asyncio as aioredis
from detector import WelfordState


class WelfordStateStore:
    """
    Stores and retrieves Welford running stats in Redis.
    Key: anomaly:stats:{user_id}:{category_id}
    No TTL — evicted by LRU when Redis maxmemory is reached.
    On cache miss, state is reconstructed from PostgreSQL (cold start).
    """

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    def _key(self, user_id: str, category_id: int) -> str:
        return f"anomaly:stats:{user_id}:{category_id}"

    async def get(self, user_id: str, category_id: int) -> WelfordState | None:
        raw = await self.redis.get(self._key(user_id, category_id))
        if not raw:
            return None
        d = json.loads(raw)
        return WelfordState(count=d["count"], mean=d["mean"], M2=d["M2"])

    async def save(self, user_id: str, category_id: int, state: WelfordState) -> None:
        await self.redis.set(
            self._key(user_id, category_id),
            json.dumps({"count": state.count, "mean": state.mean, "M2": state.M2}),
        )
