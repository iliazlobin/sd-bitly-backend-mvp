"""URL service — business logic for creating, looking up, and tracking URLs.

This module is the single source of business logic. Routers call these
functions; they never touch the database or Redis directly.
"""

import secrets
from datetime import UTC, datetime
from urllib.parse import urlparse, urlunparse

import redis.asyncio as aioredis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.url import URL
from ..schemas.url import StatsResponse, URLResponse
from .codec import base62_encode

REDIRECT_CACHE_TTL = 86400  # 24 hours


def canonicalize_url(raw: str) -> str:
    """Normalize a URL for storage: lowercase scheme+host, strip default
    ports (80/443), strip fragment. Query string is preserved.

    Raises ValueError if the URL is unparseable or missing a scheme.
    """
    if not raw or not raw.strip():
        raise ValueError("long_url is required")

    parsed = urlparse(raw.strip())

    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Invalid URL format")

    # Lowercase scheme and host.
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip default ports.
    if ":" in netloc:
        host, port_str = netloc.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            pass
        else:
            if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
                netloc = host

    # Reassemble: strip fragment, preserve path/query.
    result = urlunparse((scheme, netloc, parsed.path or "/", parsed.params, parsed.query, ""))
    return result


async def create_url(
    db: AsyncSession,
    redis: aioredis.Redis,
    long_url: str,
    *,
    custom_alias: str | None = None,
    expires_at: datetime | None = None,
    base_url: str = "http://localhost:8000",
) -> URLResponse:
    """Create a short URL.

    For auto-generated codes: INSERT → encode the returned id → UPDATE short_code.
    For custom aliases: INSERT with the alias; UNIQUE constraint catches collisions.
    Both paths warm the Redis redirect cache.
    """
    canonical = canonicalize_url(long_url)

    if custom_alias is not None:
        # Custom alias path — validate and insert directly.
        url_row = URL(
            short_code=custom_alias,
            long_url=canonical,
            expires_at=expires_at,
        )
        db.add(url_row)
        try:
            await db.flush()
        except Exception:
            await db.rollback()
            raise
        short_code = custom_alias
    else:
        # Auto-generated path — two-step: INSERT with unique placeholder, encode id, UPDATE.
        placeholder = f"_tmp_{secrets.token_hex(4)}"
        url_row = URL(
            short_code=placeholder,  # unique placeholder; replaced below
            long_url=canonical,
            expires_at=expires_at,
        )
        db.add(url_row)
        await db.flush()
        await db.refresh(url_row)

        short_code = base62_encode(url_row.id)
        url_row.short_code = short_code
        await db.flush()

    await db.commit()
    await db.refresh(url_row)

    # Warm the redirect cache.
    await redis.set(f"url:{short_code}", canonical, ex=REDIRECT_CACHE_TTL)

    return URLResponse(
        short_code=short_code,
        short_url=f"{base_url.rstrip('/')}/{short_code}",
        long_url=canonical,
        clicks=url_row.clicks,
        created_at=url_row.created_at,
        expires_at=url_row.expires_at,
    )


async def lookup_url(
    db: AsyncSession,
    redis: aioredis.Redis,
    short_code: str,
) -> tuple[str, bool] | None:
    """Look up a short code and return (long_url, is_expired).

    Returns None if the short code does not exist.
    Check Redis first; on miss, query PostgreSQL and populate Redis.
    """
    # Validate the short_code format before hitting any store.
    if not short_code or len(short_code) > 20:
        return None

    # Helper: make a datetime UTC-aware if it is naive (SQLite returns naive).
    def _ensure_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt

    now = datetime.now(UTC)

    # Check Redis cache first.
    cached = await redis.get(f"url:{short_code}")
    if cached is not None:
        # Redis may return bytes; normalize to str.
        long_url = cached.decode("utf-8") if isinstance(cached, bytes) else cached
        # We have the long_url cached; still need to check expiry
        # by querying the DB (or we could cache expires_at too).
        # For simplicity, query the DB for expiry check on cache hit.
        row = await db.execute(select(URL.expires_at).where(URL.short_code == short_code))
        expires_at = row.scalar_one_or_none()
        # If row is None, the cache was stale (shouldn't happen, but handle it).
        if expires_at is None:
            # Stale cache entry — delete it and fall through to DB path.
            await redis.delete(f"url:{short_code}")
        elif _ensure_utc(expires_at) < now:
            await redis.delete(f"url:{short_code}")
            return (long_url, True)
        else:
            return (long_url, False)

    # Cache miss — query PostgreSQL.
    row = await db.execute(select(URL.long_url, URL.expires_at).where(URL.short_code == short_code))
    result = row.one_or_none()
    if result is None:
        return None

    long_url, expires_at = result

    if expires_at is not None and _ensure_utc(expires_at) < now:
        # Expired — delete any stale Redis key and return expired.
        await redis.delete(f"url:{short_code}")
        return (long_url, True)

    # Populate Redis cache.
    await redis.set(f"url:{short_code}", long_url, ex=REDIRECT_CACHE_TTL)
    return (long_url, False)


async def increment_clicks(db: AsyncSession, short_code: str) -> None:
    """Atomically increment the click counter for *short_code*."""
    await db.execute(update(URL).where(URL.short_code == short_code).values(clicks=URL.clicks + 1))
    await db.commit()


async def get_stats(
    db: AsyncSession,
    short_code: str,
) -> StatsResponse | None:
    """Return stats for *short_code*, or None if not found."""
    row = await db.execute(select(URL).where(URL.short_code == short_code))
    url = row.scalar_one_or_none()
    if url is None:
        return None
    return StatsResponse.model_validate(url)
