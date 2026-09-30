"""REST Webhook Publisher — sends events to observer URLs via HTTP POST."""

import os
import logging
import httpx
from publishers.base import INotificationPublisher

logger = logging.getLogger(__name__)


class RestWebhookPublisher(INotificationPublisher):
    """
    Prototype publisher: posts events to registered observer URLs.
    Observer URLs are configured via the NOTIFICATION_OBSERVERS env var.
    """

    def __init__(self):
        self.observer_urls = [
            url.strip()
            for url in os.getenv("NOTIFICATION_OBSERVERS", "").split(",")
            if url.strip()
        ]

    async def publish(self, event: dict) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for url in self.observer_urls:
                try:
                    await client.post(url, json=event)
                except Exception as e:
                    # Non-blocking: observer failure does not fail ingestion
                    logger.warning(f"Observer notification failed to {url}: {e}")
