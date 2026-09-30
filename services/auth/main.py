"""Auth Service — FastAPI Application Entrypoint."""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from models import Base
from routers import auth_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=100, max_overflow=400)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """Provide an async database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    logger.info("Auth Service starting up...")
    # Override the router's get_db dependency
    app.dependency_overrides[auth_router.get_db] = get_db
    yield
    logger.info("Auth Service shutting down...")
    await engine.dispose()


app = FastAPI(
    title="Phoenix Auth Service",
    description="JWT authentication and user management",
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

# Mount router
app.include_router(auth_router.router, tags=["auth"])
