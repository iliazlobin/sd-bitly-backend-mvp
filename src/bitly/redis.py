from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

from .config import Settings

_redis_pool: aioredis.Redis | None = None


async def init_redis(settings: Settings) -> None:
    """Initialize the async Redis connection pool."""
    global _redis_pool
    _redis_pool = aioredis.from_url(settings.redis_url, decode_responses=True)


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency that yields a Redis client."""
    if _redis_pool is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    yield _redis_pool
