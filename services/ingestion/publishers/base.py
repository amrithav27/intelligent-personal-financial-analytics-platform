"""OBSERVER PATTERN — Base interface for notification publishers."""

from abc import ABC, abstractmethod


class INotificationPublisher(ABC):
    """
    OBSERVER pattern: Analytics/downstream services observe ingestion events.
    RestWebhookPublisher is used in the prototype.
    KafkaPublisher is the production implementation — swap via NOTIFICATION_BACKEND=kafka.
    """

    @abstractmethod
    async def publish(self, event: dict) -> None:
        ...
