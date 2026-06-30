"""URL router — POST /api/urls and GET /api/urls/{short_code}/stats.

Thin layer: parse request, delegate to services, serialize response.
Zero business logic.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import exc as sa_exc
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..database import get_session
from ..redis import get_redis
from ..schemas.url import CreateURLRequest, StatsResponse, URLResponse
from ..services import rate_limiter, url_service

router = APIRouter(prefix="/api/urls", tags=["urls"])


def _get_settings() -> Settings:
    return Settings()


@router.post("", status_code=201, response_model=URLResponse)
async def create_url(
    body: CreateURLRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
    redis=Depends(get_redis),
    settings: Settings = Depends(_get_settings),
) -> URLResponse:
    """Create a short URL with rate limiting."""
    # --- Rate limit check ---
    ip = request.client.host if request.client else "127.0.0.1"
    allowed = await rate_limiter.check_rate_limit(
        redis,
        ip,
        limit=settings.rate_limit_requests,
        window_s=settings.rate_limit_window_s,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "1"},
        )

    # --- Create the URL ---
    base_url = str(request.base_url).rstrip("/")

    try:
        result = await url_service.create_url(
            db,
            redis,
            body.long_url,
            custom_alias=body.custom_alias,
            expires_at=body.expires_at,
            base_url=base_url,
        )
    except sa_exc.IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Alias '{body.custom_alias}' is already taken",
        ) from None

    return result


@router.get("/{short_code}/stats", response_model=StatsResponse)
async def get_stats(
    short_code: str,
    db: AsyncSession = Depends(get_session),
) -> StatsResponse:
    """Return click stats for a short URL."""
    result = await url_service.get_stats(db, short_code)
    if result is None:
        raise HTTPException(status_code=404, detail="Short code not found")
    return result
