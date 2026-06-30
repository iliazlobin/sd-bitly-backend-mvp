"""Functional test fixtures for the Bitly app.

Uses SQLite (in-memory) and fakeredis for fast, isolated tests.
Does NOT use the real lifespan — DB/Redis are provided via dependency overrides.
"""

from collections.abc import AsyncGenerator, AsyncIterator

import pytest_asyncio
from fakeredis import aioredis as fake_aioredis
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.bitly.database import Base, get_session
from src.bitly.models import (
    URL,  # noqa: F401  # ensure model registered before create_all
)
from src.bitly.redis import get_redis as original_get_redis

TEST_DATABASE_URL = "sqlite+aiosqlite://"


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Fresh SQLite engine + tables for each test.

    In-memory SQLite gives each connection its own private database, so the
    connection that runs ``create_all`` is not the one the test queries use —
    hence ``no such table``. ``StaticPool`` pins a single shared connection so
    the schema and the queries see the same in-memory DB.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_sessionmaker(test_engine):
    """Sessionmaker bound to the test engine."""
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function")
async def fake_redis() -> AsyncIterator[fake_aioredis.FakeRedis]:
    """Fresh fakeredis instance for each test."""
    r = fake_aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest_asyncio.fixture(scope="function")
async def app(
    test_sessionmaker,
    fake_redis: fake_aioredis.FakeRedis,
) -> AsyncIterator[FastAPI]:
    """Test FastAPI app with SQLite + fakeredis overrides.

    We build the app manually (no lifespan) so that init_db/init_redis
    don't try to connect to real services.
    """
    from fastapi import FastAPI as _FastAPI

    from src.bitly.routers import redirect, urls

    app = _FastAPI(title="Bitly Test", version="0.1.0")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "healthy"}

    app.include_router(urls.router)
    app.include_router(redirect.router)

    # Override the session dependency.
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            try:
                yield session
            finally:
                await session.close()

    # Override the redis dependency.
    async def override_get_redis() -> AsyncGenerator[fake_aioredis.FakeRedis, None]:
        yield fake_redis

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[original_get_redis] = override_get_redis

    yield app

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async httpx client for the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
