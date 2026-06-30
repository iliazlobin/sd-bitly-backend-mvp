"""Redirect router — GET /{short_code}.

Resolves a short code to a 301 redirect, with Redis caching.
Increments the click counter synchronously (atomic UPDATE, negligible latency).
"""

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..redis import get_redis
from ..services import url_service

router = APIRouter(tags=["redirect"])

_SHORT_CODE_RE = re.compile(r"^[0-9a-zA-Z]{1,20}$")


@router.get("/{short_code}")
async def redirect(
    short_code: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    redis=Depends(get_redis),
):
    """Resolve a short code to a 301 redirect, or return 404/410."""
    # Validate format before hitting stores.
    if not _SHORT_CODE_RE.match(short_code):
        raise HTTPException(status_code=404, detail="Short code not found")

    result = await url_service.lookup_url(db, redis, short_code)

    if result is None:
        raise HTTPException(status_code=404, detail="Short code not found")

    long_url, is_expired = result

    if is_expired:
        raise HTTPException(status_code=410, detail="This link has expired")

    # Increment click counter synchronously — negligible latency (~1ms).
    await url_service.increment_clicks(db, short_code)

    return RedirectResponse(
        url=long_url,
        status_code=301,
        headers={"Cache-Control": "private, max-age=90"},
    )
