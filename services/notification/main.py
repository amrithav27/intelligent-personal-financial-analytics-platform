"""Notification Service — FastAPI Entrypoint with WebSocket support."""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import redis.asyncio as aioredis

from routers import alert_router, ws_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Notification Service starting up...")
    yield
    logger.info("Notification Service shutting down...")
    await engine.dispose()


app = FastAPI(
    title="Phoenix Notification Service",
    description="Real-time alerts via WebSocket + alert storage",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(alert_router.router, tags=["alerts"])
app.include_router(ws_router.router, tags=["websocket"])


@app.get("/health/ready")
async def health_ready():
    return {"status": "ok", "service": "notification"}
