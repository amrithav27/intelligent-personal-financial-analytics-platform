"""
Kafka Publisher — production stub for event-driven architecture.
TODO:KAFKA — Replace RestWebhookPublisher with this class in production.
Set NOTIFICATION_BACKEND=kafka in docker-compose.yml to activate.
Payload schema is 100% compatible — no schema migration required.
"""

from publishers.base import INotificationPublisher


class KafkaPublisher(INotificationPublisher):
    def __init__(self):
        # from confluent_kafka import Producer
        # self.producer = Producer({"bootstrap.servers": os.environ["KAFKA_BOOTSTRAP"]})
        raise NotImplementedError(
            "KafkaPublisher not yet enabled. Set NOTIFICATION_BACKEND=rest."
        )

    async def publish(self, event: dict) -> None:
        # self.producer.produce("transactions.ingested", value=json.dumps(event).encode())
        # self.producer.flush()
        pass
