"""Ingestion Service — FastAPI Application Entrypoint."""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from publishers.rest_webhook_publisher import RestWebhookPublisher
from publishers.kafka_publisher import KafkaPublisher
from routers import ingest_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=100, max_overflow=400)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Select publisher based on env var
_publisher = None


def get_publisher():
    global _publisher
    if _publisher is None:
        backend = os.getenv("NOTIFICATION_BACKEND", "rest")
        if backend == "kafka":
            _publisher = KafkaPublisher()
        else:
            _publisher = RestWebhookPublisher()
    return _publisher


async def get_db():
    """Provide an async database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_publisher_dep():
    return get_publisher()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    logger.info("Ingestion Service starting up...")
    app.dependency_overrides[ingest_router.get_db] = get_db
    app.dependency_overrides[ingest_router.get_publisher] = get_publisher_dep
    yield
    logger.info("Ingestion Service shutting down...")
    await engine.dispose()


app = FastAPI(
    title="Phoenix Ingestion Service",
    description="Transaction ingestion with Adapter pattern",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router.router, prefix="/transactions", tags=["transactions"])


@app.get("/health/ready")
async def health_ready():
    return {"status": "ok", "service": "ingestion"}
