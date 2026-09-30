"""Redis Cache Invalidation — evicts stale user data after analytics computation."""

import logging
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class CacheInvalidator:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def invalidate_user(self, user_id: str, month: str | None = None) -> None:
        """
        Called after every Analytics Engine computation cycle.
        Evicts all cached data for the affected user.
        """
        keys_to_delete = [
            f"fhs:{user_id}",
            f"dashboard:{user_id}:overview",
        ]
        if month:
            keys_to_delete.append(f"cat_dist:{user_id}:{month}")

        if keys_to_delete:
            await self.redis.delete(*keys_to_delete)
            logger.info(f"Cache invalidated for user {user_id}: {keys_to_delete}")
