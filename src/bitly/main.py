"""Bitly URL Shortener — FastAPI application factory."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from .config import Settings
from .database import close_db, init_db
from .redis import close_redis, init_redis
from .routers import redirect, urls

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Application lifespan: init DB and Redis on startup, close on shutdown."""
    await init_db(settings)
    await init_redis(settings)
    yield
    await close_redis()
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Route ordering is intentional:
    1. /healthz (literal — matched first)
    2. /api/*   (API routes — matched second)
    3. /{short_code} (redirect catch-all — matched last)
    """
    app = FastAPI(
        title="Bitly URL Shortener",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "healthy"}

    # Mount API routes before the redirect catch-all.
    app.include_router(urls.router)
    app.include_router(redirect.router)

    return app


app = create_app()
