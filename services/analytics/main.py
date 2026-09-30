"""Analytics Engine — FastAPI Application Entrypoint."""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import redis.asyncio as aioredis

from routers import analytics_router, internal_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=100, max_overflow=400)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
redis_client: aioredis.Redis | None = None


async def get_db():
    """Generic DB session — no RLS context set. Used for internal/service endpoints."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_redis():
    return redis_client


def get_db_for_user(user_id: str):
    """
    Repository Pattern: Returns a DB session with the PostgreSQL session variable
    `app.current_user_id` set to the given user_id.

    This satisfies the RLS policy:
        USING (user_id = nullif(current_setting('app.current_user_id', true), '')::UUID)

    `SET LOCAL` scopes the variable to the current transaction only, ensuring
    no cross-request contamination even in a connection pool environment.

    NOTE: PostgreSQL's SET LOCAL does not support bind parameters ($1 / :name).
    We validate user_id as a proper UUID and embed it as a literal to avoid
    the asyncpg "syntax error at or near $1" error.
    """
    import uuid as _uuid
    # Validate: will raise ValueError if malformed — prevents SQL injection
    safe_uid = str(_uuid.UUID(user_id))

    async def _get_db():
        async with async_session() as session:
            try:
                # SET LOCAL does not accept bind params; embed validated UUID literal
                await session.execute(
                    text(f"SET LOCAL app.current_user_id = '{safe_uid}'")
                )
                yield session
            finally:
                await session.close()
    return _get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    logger.info("Analytics Engine starting up...")
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)

    llm_status = "ENABLED" if os.getenv("ENABLE_LLM_CATEGORIZATION", "false").lower() == "true" else "DISABLED"
    logger.info(f"LLM categorization: {llm_status}")

    # Override dependencies
    app.dependency_overrides[analytics_router.get_db] = get_db
    app.dependency_overrides[analytics_router.get_redis] = get_redis
    app.dependency_overrides[internal_router.get_db] = get_db
    app.dependency_overrides[internal_router.get_redis] = get_redis

    # Expose the user-scoped DB factory so analytics_router can reference it
    app.state.get_db_for_user = get_db_for_user

    yield
    logger.info("Analytics Engine shutting down...")
    if redis_client:
        await redis_client.close()
    await engine.dispose()


app = FastAPI(
    title="Phoenix Analytics Engine",
    description="Financial analytics with Strategy and Factory patterns",
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

app.include_router(analytics_router.router, tags=["analytics"])
app.include_router(internal_router.router, tags=["internal"])


@app.get("/health/ready")
async def health_ready():
    return {"status": "ok", "service": "analytics"}
