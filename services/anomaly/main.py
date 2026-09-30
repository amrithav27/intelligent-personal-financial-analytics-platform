"""Anomaly Detection Service — FastAPI Entrypoint."""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import redis.asyncio as aioredis

from routers import anomaly_router, internal_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
redis_client: aioredis.Redis | None = None


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_redis():
    return redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    logger.info("Anomaly Detection Service starting up...")
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    app.dependency_overrides[anomaly_router.get_db] = get_db
    app.dependency_overrides[internal_router.get_db] = get_db
    app.dependency_overrides[internal_router.get_redis] = get_redis
    yield
    logger.info("Anomaly Detection Service shutting down...")
    if redis_client:
        await redis_client.close()
    await engine.dispose()


app = FastAPI(
    title="Phoenix Anomaly Detection Service",
    description="Z-score anomaly detection with Welford's algorithm",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(anomaly_router.router, prefix="/alerts", tags=["anomaly"])
app.include_router(internal_router.router, tags=["internal"])


@app.get("/health/ready")
async def health_ready():
    return {"status": "ok", "service": "anomaly"}
