"""Recommendation Service — FastAPI Entrypoint."""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from routers import recommendation_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Recommendation Service starting up...")
    app.dependency_overrides[recommendation_router.get_db] = get_db
    yield
    logger.info("Recommendation Service shutting down...")
    await engine.dispose()


app = FastAPI(
    title="Phoenix Recommendation Service",
    description="Budget recommendations with Strategy pattern (50/30/20 + statistical)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(recommendation_router.router, prefix="/recommendations", tags=["recommendations"])


@app.get("/health/ready")
async def health_ready():
    return {"status": "ok", "service": "recommendation"}
